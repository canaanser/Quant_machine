"""
扫描调度器（scanner_scheduler.py）
============================================
把手动测试脚本（test_scanner_v2.py）升级为可自动运行的任务。

能力：
  1. 多股票扫描（tickers 列表）
  2. 全量 / 增量两种模式（增量基于 scan_progress 断点）
  3. 错误隔离：单只股票失败不中断整轮，记录日志继续下一只
  4. 日志输出：控制台 + outputs/logs/scanner_YYYYMMDD.log
  5. 命令行入口 + API 两种调用方式

核心扫描逻辑（scan_symbol）与 test_scanner_v2.py 共用同一套算法：
  全量 detect_waves 波段识别（无滑动窗口覆盖空洞）
  → 按波段 scan_patterns（幂等写入，data_writer 层去重）
  → 位置映射回写 → pending 回填 ready

用法：
  # API
  from structure_engine.scanner.scanner_scheduler import ScannerScheduler
  sched = ScannerScheduler(tickers=["000063", "600498"], mode="incremental")
  sched.run_once()

  # 命令行（全量扫描）
  python -m structure_engine.scanner.scanner_scheduler --mode full --tickers 000063,600498

  # 定时循环（每24小时一轮，Ctrl+C 停止）
  python -m structure_engine.scanner.scanner_scheduler --mode incremental --interval 24
"""

import argparse
import logging
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
LOG_DIR = PROJECT_ROOT / "outputs" / "logs"

from core.data_loader import load_data
from config.config import SCAN_TICKERS
from structure_engine.scanner.wave_detector import detect_waves
from structure_engine.scanner.pattern_scanner import scan_patterns
from structure_engine.scanner.position_mapper import (
    backfill_band_positions, backfill_positions_for_results,
)
from structure_engine.scanner import data_writer as data_writer_module
from structure_engine.scanner.data_writer import (
    get_pattern_history_count,
    update_scan_progress,
    get_last_scan_progress,
    close_global_connection,
    get_global_connection,
    write_wave_history,
    set_batch_mode,
)

# ===== 日志配置 =====
logger = logging.getLogger("scanner_scheduler")


def setup_logging(verbose: bool = True):
    """配置日志：控制台 + 文件（outputs/logs/scanner_YYYYMMDD.log）"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        fh = logging.FileHandler(LOG_DIR / f"scanner_{datetime.now().strftime('%Y%m%d')}.log", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        if verbose:
            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            logger.addHandler(sh)


def _write_scan_results(symbol, ohlc, all_waves, all_results, mode="incremental"):
    """写库阶段（2026-08-28 小二陈）：统一在主进程执行（单写者 = 令牌语义）
    写 wave + 批量写 pattern/atomic + 位置映射回写 + pending + 处境/冷却 + 断点 + commit"""
    result = {"symbol": symbol, "mode": mode, "days": len(ohlc), "waves": len(all_waves),
              "patterns": len(all_results), "updated": 0, "backfilled": 0,
              "total_records": 0, "situation_backfilled": 0, "error": None}

    from structure_engine.scanner.data_writer import write_pattern_history, write_atomic_features

    # 批量写入模式（攒批减少 fsync）
    set_batch_mode(True)

    # ---------- 写波段 ----------
    for wave in all_waves:
        try:
            write_wave_history(symbol, wave, scan_version=1)
        except Exception as e:
            logger.warning("  ⚠️ 写入波段失败: %s", e)

    # ---------- 写形态 + 原子特征（results 已带全字段） ----------
    for r in all_results:
        try:
            meta = r.get('meta') or {}
            is_ready = meta.get('band_position_ready', 0)
            updated_at = datetime.now().isoformat() if is_ready else None
            write_pattern_history(
                symbol=symbol,
                pattern_id=r['pattern_id'],
                pattern_name=r.get('pattern_type'),
                category=r.get('category'),
                match_date=str(r['date']),
                match_price=r.get('match_price'),
                open_price=r.get('open_price'),
                peak_date=meta.get('peak_date'),
                valley_date=meta.get('valley_date'),
                band_position=meta.get('band_position'),
                band_progress=0.0,
                band_direction=None,
                wave_id=None,
                band_position_ready=is_ready,
                band_position_updated_at=updated_at,
                return_1d=r.get('r1d'), return_2d=r.get('r2d'), return_3d=r.get('r3d'),
                return_4d=r.get('r4d'), return_5d=r.get('r5d'),
                return_10d=meta.get('return_10d'),
                return_20d=meta.get('return_20d'),
                composite_return=meta.get('composite_return'),
                signed_score=meta.get('signed_score'),
                base_score=meta.get('base_score'),
                scan_version=1
            )
            write_atomic_features(symbol=symbol, date=str(r['date']),
                                  pattern_id=r['pattern_id'], atom_values=meta.get('atomics'))
        except Exception as e:
            logger.warning("  ⚠️ 形态写入失败 %s: %s", r.get('date'), e)

    # ---------- 位置映射回写 ----------
    try:
        get_global_connection().commit()  # 解除 batch 自锁
    except Exception:
        pass
    try:
        update_count, fail_count = backfill_positions_for_results(symbol, all_results, ohlc, all_waves)
        result["updated"] = update_count
        logger.info("  ✅ 位置映射回写 %d 条（%d 条未匹配）", update_count, fail_count)
    except Exception as e:
        logger.warning("  ⚠️ 位置映射回写异常: %s", e)

    # ---------- pending 回填 ----------
    try:
        backfill_total = 0
        for wave in all_waves:
            try:
                backfill_total += backfill_band_positions(symbol, wave, ohlc, data_writer_module)
            except Exception as e:
                logger.warning("  ⚠️ 回填失败: %s", e)
        result["backfilled"] = backfill_total
        logger.info("  ✅ 共回填 %d 条记录为 ready", backfill_total)
    except Exception as e:
        logger.warning("  ⚠️ pending 回填异常: %s", e)

    # ---------- 处境/冷却回填 ----------
    try:
        sit_total = backfill_situation_cooldown(symbol, ohlc, data_writer_module)
        result["situation_backfilled"] = sit_total
    except Exception as e:
        logger.warning("  ⚠️ 处境/冷却回填异常: %s", e)

    # ---------- 断点 + 统计 + 提交 ----------
    if len(ohlc) > 0:
        last_date = ohlc.index[-1]
        last_date_str = last_date.strftime('%Y-%m-%d') if hasattr(last_date, 'strftime') else str(last_date)
        update_scan_progress(symbol=symbol, last_scanned_date=last_date_str,
                             last_window_start=last_date_str, scan_mode=mode, scan_version=1)
        logger.info("  ✅ 扫描进度已更新到: %s", last_date_str)
    result["total_records"] = get_pattern_history_count(symbol)
    logger.info("  ✅ %s pattern_history 记录数: %d", symbol, result["total_records"])

    set_batch_mode(False)
    try:
        get_global_connection().commit()
    except Exception:
        pass
    return result


def identify_symbol(symbol, start="2016-01-01", end=None, mode="incremental",
                    min_amplitude=0.08, lookback=5):
    """识别阶段（2026-08-28 小二陈）：加载 + 波段识别 + 形态匹配，纯内存不写库。
    返回 (symbol, ohlc, all_waves, all_results, error)；error 非 None 表示该股跳过"""
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    if symbol and symbol.isdigit() and len(symbol) < 6:
        symbol = symbol.zfill(6)

    # ---------- 1. 加载 ----------
    market_data = load_data(
        source='freestockdb', tickers=[symbol], start=start, end=end, frequency="1d", fq="qfq"
    )
    ohlc = market_data.get_ohlc(symbol)
    if ohlc is None or ohlc.empty:
        return (symbol, None, None, None, "无数据")
    logger.info("  ✅ 加载 %d 个交易日（%s ~ %s）", len(ohlc), ohlc.index.min(), ohlc.index.max())

    # ---------- 2. 增量截取 ----------
    if mode == "incremental":
        progress = get_last_scan_progress(symbol)
        if progress:
            last_date = progress['last_scanned_date']
            if last_date in ohlc.index:
                ohlc = ohlc.loc[last_date:]
            else:
                ohlc = ohlc[ohlc.index >= last_date]
            logger.info("  📌 本次扫描新增 %d 个交易日", len(ohlc))
        else:
            logger.info("  📌 未找到扫描进度，执行全量扫描")
    if len(ohlc) < 5:
        return (symbol, None, None, None, "数据不足5天")

    # ---------- 3. 波段识别 ----------
    all_waves = detect_waves(
        df=ohlc, window_days=len(ohlc), lookback=lookback, min_amplitude=min_amplitude
    )

    # ---------- 4. 形态匹配（不写库） ----------
    all_results = []
    for wave in all_waves:
        peak_date = wave.get('peak_date')
        valley_date = wave.get('valley_date')
        if not peak_date or not valley_date:
            continue
        start_date = peak_date if wave.get('direction') == 'down' else valley_date
        end_date = valley_date if wave.get('direction') == 'down' else peak_date
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        try:
            end_idx_global = ohlc.index.get_loc(end_date) if end_date in ohlc.index else -1
            if end_idx_global == -1:
                continue
            start_idx_global = ohlc.index.get_loc(start_date)
            extended_end_idx_global = min(end_idx_global + 20, len(ohlc) - 1)
            wave_df = ohlc.iloc[start_idx_global:extended_end_idx_global + 1]
        except Exception:
            continue
        if len(wave_df) < 5:
            continue
        try:
            results = scan_patterns(
                df=wave_df, debug=False, write_to_db=False, symbol=symbol,
                peak_date=wave['peak_date'], valley_date=wave['valley_date'], band_position=None
            )
        except Exception as e:
            logger.warning("  ⚠️ 波段扫描失败 %s~%s: %s", start_date, end_date, e)
            continue
        for r in results:
            r['_wave'] = wave
            all_results.append(r)

    logger.info("  ✅ 识别到 %d 个波段，匹配到 %d 个形态", len(all_waves), len(all_results))
    return (symbol, ohlc, all_waves, all_results, None)


def _identify_worker(args):
    """Pool worker 入口（Windows spawn 需要顶层函数，参数必须可 pickle）"""
    symbol, start, end, mode, min_amplitude, lookback = args
    try:
        return identify_symbol(symbol, start=start, end=end, mode=mode,
                               min_amplitude=min_amplitude, lookback=lookback)
    except Exception as e:
        return (symbol, None, None, None, f"识别异常: {e}")


def scan_symbol(
    symbol: str,
    start: str = "2016-01-01",
    end: Optional[str] = None,
    mode: str = "incremental",
    min_amplitude: float = 0.08,
    lookback: int = 5,
) -> dict:
    """
    扫描单只股票（核心扫描函数，test 脚本与调度器共用）

    参数：
        symbol: 股票代码（如 '000063'）
        start: 数据起始日期（全量模式的有效起点）
        end: 数据结束日期（默认今天）
        mode: 'full' 全量 / 'incremental' 增量（基于 scan_progress 断点）
        min_amplitude: 波段最小振幅
        lookback: 峰谷确认回看窗口

    返回：
        {symbol, mode, days, waves, patterns, updated, backfilled, total_records, error}
    """
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    result = {"symbol": symbol, "mode": mode, "days": 0, "waves": 0,
              "patterns": 0, "updated": 0, "backfilled": 0, "total_records": 0, "error": None}

    # 防御：股票代码补前导零（PowerShell 会把 002309 解析成 2309）
    if symbol and symbol.isdigit() and len(symbol) < 6:
        symbol = symbol.zfill(6)

    # 性能优化：批量写入模式（攒批减少 fsync，结尾统一 commit）
    set_batch_mode(True)

    logger.info("=" * 60)
    logger.info("扫描 %s（模式：%s，区间 %s ~ %s）", symbol, mode, start, end)
    logger.info("=" * 60)

    # ---------- 1. 加载数据 ----------
    market_data = load_data(
        source='freestockdb',
        tickers=[symbol],
        start=start,
        end=end,
        frequency="1d",
        fq="qfq"
    )
    ohlc = market_data.get_ohlc(symbol)
    if ohlc is None or ohlc.empty:
        result["error"] = "无数据"
        logger.error("  ❌ %s 无数据，跳过", symbol)
        set_batch_mode(False)
        return result
    logger.info("  ✅ 加载 %d 个交易日（%s ~ %s）", len(ohlc), ohlc.index.min(), ohlc.index.max())

    # ---------- 2. 增量模式：从断点截取 ----------
    if mode == "incremental":
        progress = get_last_scan_progress(symbol)
        if progress:
            last_date = progress['last_scanned_date']
            logger.info("  📌 上次扫描到: %s", last_date)
            if last_date in ohlc.index:
                ohlc = ohlc.loc[last_date:]
            else:
                ohlc = ohlc[ohlc.index >= last_date]
            logger.info("  📌 本次扫描新增 %d 个交易日", len(ohlc))
        else:
            logger.info("  📌 未找到扫描进度，执行全量扫描")

    if len(ohlc) < 5:
        logger.info("  ⚠️ 新增数据不足5天，跳过扫描")
        set_batch_mode(False)
        return result

    # ---------- 3. 全量波段识别（无滑动窗口覆盖空洞） ----------
    all_waves = detect_waves(
        df=ohlc,
        window_days=len(ohlc),
        lookback=lookback,
        min_amplitude=min_amplitude
    )
    result["waves"] = len(all_waves)
    result["days"] = len(ohlc)

    # ---------- 4. 按波段扫描形态 ----------
    # 2026-08-28：写库（wave/pattern/回填）统一移到 _write_scan_results（主进程令牌写入）
    all_results = []
    for wave in all_waves:
        peak_date = wave.get('peak_date')
        valley_date = wave.get('valley_date')
        if not peak_date or not valley_date:
            continue

        start_date = peak_date if wave.get('direction') == 'down' else valley_date
        end_date = valley_date if wave.get('direction') == 'down' else peak_date
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        try:
            end_idx_global = ohlc.index.get_loc(end_date) if end_date in ohlc.index else -1
            if end_idx_global == -1:
                continue
            start_idx_global = ohlc.index.get_loc(start_date)
            extended_end_idx_global = min(end_idx_global + 20, len(ohlc) - 1)
            wave_df = ohlc.iloc[start_idx_global:extended_end_idx_global + 1]
        except Exception:
            continue

        if len(wave_df) < 5:
            continue

        try:
            results = scan_patterns(
                df=wave_df,
                debug=False,
                write_to_db=False,  # 2026-08-28：识别不写库，统一主进程写
                symbol=symbol,
                peak_date=wave['peak_date'],
                valley_date=wave['valley_date'],
                band_position=None
            )
        except Exception as e:
            logger.warning("  ⚠️ 波段扫描失败 %s~%s: %s", start_date, end_date, e)
            continue

        for r in results:
            r['_wave'] = wave
            all_results.append(r)

    result["patterns"] = len(all_results)
    logger.info("  ✅ 识别到 %d 个波段，匹配到 %d 个形态", len(all_waves), len(all_results))

    # ---------- 5+ 写库阶段（统一主进程执行，2026-08-28） ----------
    return _write_scan_results(symbol, ohlc, all_waves, all_results, mode)


class ScannerScheduler:
    """扫描调度器：管理多股票、多模式的扫描任务"""

    def __init__(
        self,
        tickers: List[str],
        start: str = "2016-01-01",
        end: Optional[str] = None,
        mode: str = "incremental",
        min_amplitude: float = 0.08,
        lookback: int = 5,
        verbose: bool = True,
        workers: int = 1,
    ):
        self.tickers = tickers
        self.start = start
        self.end = end
        self.mode = mode
        self.min_amplitude = min_amplitude
        self.lookback = lookback
        self.workers = max(1, int(workers))
        setup_logging(verbose)

    def run_once(self) -> dict:
        """执行一轮扫描：遍历所有配置股票，单只失败不中断整轮。
        workers>1 时：识别阶段多进程并行（纯内存），写库阶段主进程串行（单写者=令牌语义）"""
        logger.info("\n🚀 调度器启动一轮扫描（%d 只股票，模式=%s，workers=%d）",
                    len(self.tickers), self.mode, self.workers)
        results = {}
        if self.workers > 1 and len(self.tickers) > 1:
            from multiprocessing import Pool
            tasks = [(s, self.start, self.end, self.mode, self.min_amplitude, self.lookback)
                     for s in self.tickers]
            with Pool(processes=self.workers) as pool:
                for item in pool.imap_unordered(_identify_worker, tasks):
                    if item is None:
                        continue
                    symbol, ohlc, all_waves, all_results, err = item
                    if err:
                        logger.error("  ❌ %s 识别跳过: %s", symbol, err)
                        results[symbol] = {"symbol": symbol, "error": err}
                        continue
                    logger.info("\n📦 写库 %s（识别 %d 波段 / %d 形态）", symbol,
                                len(all_waves), len(all_results))
                    try:
                        results[symbol] = _write_scan_results(
                            symbol, ohlc, all_waves, all_results, self.mode)
                    except Exception as e:
                        logger.error("  ❌ %s 写库异常: %s\n%s", symbol, e, traceback.format_exc())
                        results[symbol] = {"symbol": symbol, "error": str(e)}
        else:
            for symbol in self.tickers:
                try:
                    results[symbol] = scan_symbol(
                        symbol=symbol,
                        start=self.start,
                        end=self.end,
                        mode=self.mode,
                        min_amplitude=self.min_amplitude,
                        lookback=self.lookback,
                    )
                except Exception as e:
                    logger.error("  ❌ %s 扫描异常: %s\n%s", symbol, e, traceback.format_exc())
                    results[symbol] = {"symbol": symbol, "error": str(e)}
                finally:
                    close_global_connection()
        logger.info("\n🏁 本轮扫描完成")
        return results

    def run_loop(self, interval_hours: float = 24.0):
        """定时循环：每隔 interval_hours 小时执行一轮（Ctrl+C 停止）"""
        logger.info("⏰ 定时循环启动，间隔 %.1f 小时", interval_hours)
        try:
            while True:
                self.run_once()
                logger.info("💤 休眠 %.1f 小时后执行下一轮...", interval_hours)
                time.sleep(interval_hours * 3600)
        except KeyboardInterrupt:
            logger.info("🛑 收到中断信号，调度器停止")



def backfill_situation_cooldown(symbol: str, ohlc, data_writer_module) -> int:
    """回填 V3 处境与冷却字段（2026-08-27 老板确认）
    - drawdown_from_peak: 近120日高点回撤深度（先验可算）
    - days_since_peak: 距近120日高点天数
    - cooldown_days: 距该股该形态上次出现天数（冷却期）
    用完整 ohlc 逐条 UPDATE，无未来函数（只用截至 match_date 的数据）。
    """
    import numpy as np
    conn = data_writer_module.get_global_connection()
    cursor = conn.cursor()

    # 取该股所有已写入的形态记录（按日期排序）
    rows = cursor.execute("""
        SELECT record_id, substr(match_date,1,10), pattern_id
        FROM pattern_history WHERE symbol=? ORDER BY match_date
    """, (symbol,)).fetchall()

    # 计算每只股票的 120 日滚动高点（截至各日期）
    close = ohlc['close'].astype(float)
    date_list = list(ohlc.index)
    date_strs = [d.strftime('%Y-%m-%d') for d in date_list]

    # 预计算每个交易日的回撤深度 + 距高点天数（滚动120）
    dd_map = {}   # date_str -> (drawdown, days_since_peak)
    for i in range(len(date_list)):
        dstr = date_strs[i]
        window = close.iloc[max(0, i-120):i+1]
        peak = float(window.max())
        cur = float(close.iloc[i])
        dd = cur/peak - 1 if peak > 0 else 0.0
        peak_idx = window.idxmax()
        # 距高点天数（用索引差）
        try:
            peak_pos = list(window.index).index(peak_idx)
            days = i - (max(0, i-120) + peak_pos)
        except Exception:
            days = 0
        dd_map[dstr] = (dd, days)

    # 冷却期：按 (pattern_id) 记录上次出现日期
    # 2026-08-27：改为批量收集 + 一次 executemany（原逐条 UPDATE，量级 5000+）
    from datetime import datetime as _dt
    last_seen = {}   # pattern_id -> date_str
    updates = []
    for record_id, mdate, pattern_id in rows:
        if mdate not in dd_map:
            continue
        dd, days = dd_map[mdate]
        # 冷却天数 = 距上次同形态出现
        cooldown = None
        if pattern_id in last_seen:
            try:
                d1 = _dt.strptime(mdate, '%Y-%m-%d')
                d0 = _dt.strptime(last_seen[pattern_id], '%Y-%m-%d')
                cooldown = (d1 - d0).days
            except Exception:
                cooldown = None
        last_seen[pattern_id] = mdate

        updates.append((dd, days, cooldown, record_id))

    if updates:
        cursor.executemany("""
            UPDATE pattern_history SET drawdown_from_peak=?, days_since_peak=?, cooldown_days=?
            WHERE record_id=?
        """, updates)
    updated = len(updates)
    data_writer_module._maybe_commit(conn)
    logger.info("  ✅ 处境/冷却回填 %d 条", updated)
    return updated

def main():
    parser = argparse.ArgumentParser(description="股票形态扫描调度器")
    parser.add_argument("--tickers", default=None,
                        help="股票代码，逗号分隔；默认使用 config.SCAN_TICKERS（20只通信板块）")
    parser.add_argument("--start", default="2016-01-01", help="数据起始日期（默认 2016-01-01，10年）")
    parser.add_argument("--end", default=None, help="数据结束日期（默认今天）")
    parser.add_argument("--mode", default="incremental", choices=["full", "incremental"],
                        help="full=全量 / incremental=增量（默认）")
    parser.add_argument("--interval", type=float, default=0,
                        help="定时循环间隔（小时），0=只跑一轮（默认）")
    parser.add_argument("--min-amplitude", type=float, default=0.08, help="波段最小振幅")
    parser.add_argument("--start-at", default=None,
                        help="从指定股票代码开始扫描（跳过之前的，用于中断后续跑）")
    parser.add_argument("--workers", type=int, default=8,
                        help="并行识别进程数（默认8，12核机器；内存紧张可降为4）")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.strip().zfill(6) for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = list(SCAN_TICKERS)
        logger.info("📌 未指定 --tickers，使用 config.SCAN_TICKERS（%d 只）", len(tickers))
    # 断点续跑：--start-at 从指定股票开始（2026-08-27 小二陈，配合老板"停→续跑"）
    if args.start_at:
        sa = args.start_at.strip().zfill(6)
        if sa in tickers:
            idx = tickers.index(sa)
            tickers = tickers[idx:]
            logger.info("📌 --start-at %s：从第 %d 只开始，本次扫 %d 只", sa, idx + 1, len(tickers))
        else:
            logger.warning("⚠️ --start-at %s 不在扫描池中，忽略该参数", sa)
    sched = ScannerScheduler(
        tickers=tickers,
        start=args.start,
        end=args.end,
        mode=args.mode,
        min_amplitude=args.min_amplitude,
        workers=args.workers,
    )
    if args.interval and args.interval > 0:
        sched.run_loop(args.interval)
    else:
        sched.run_once()


if __name__ == "__main__":
    main()
