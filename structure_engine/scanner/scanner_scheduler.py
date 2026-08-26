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


def scan_symbol(
    symbol: str,
    start: str = "2023-01-01",
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

    # 写入波段历史表
    for wave in all_waves:
        try:
            write_wave_history(symbol, wave, scan_version=1)
        except Exception as e:
            logger.warning("  ⚠️ 写入波段失败: %s", e)

    # ---------- 4. 按波段扫描形态 ----------
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
                write_to_db=True,
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

    # ---------- 5. 位置映射回写（公共函数，2026-08-26 消除重复） ----------
    update_count, fail_count = backfill_positions_for_results(
        symbol, all_results, ohlc, all_waves
    )
    result["updated"] = update_count
    logger.info("  ✅ 位置映射回写 %d 条（%d 条未匹配）", update_count, fail_count)

    # ---------- 6. pending 回填 ----------
    backfill_total = 0
    for wave in all_waves:
        try:
            backfill_total += backfill_band_positions(symbol, wave, ohlc, data_writer_module)
        except Exception as e:
            logger.warning("  ⚠️ 回填失败: %s", e)
    result["backfilled"] = backfill_total
    logger.info("  ✅ 共回填 %d 条记录为 ready", backfill_total)

    # ---------- 7. 更新扫描进度 ----------
    if mode == "incremental" and len(ohlc) > 0:
        last_date = ohlc.index[-1]
        last_date_str = last_date.strftime('%Y-%m-%d') if hasattr(last_date, 'strftime') else str(last_date)
        update_scan_progress(
            symbol=symbol,
            last_scanned_date=last_date_str,
            last_window_start=last_date_str,
            scan_mode=mode,
            scan_version=1
        )
        logger.info("  ✅ 扫描进度已更新到: %s", last_date_str)

    # ---------- 8. 统计 ----------
    result["total_records"] = get_pattern_history_count(symbol)
    logger.info("  ✅ %s pattern_history 记录数: %d", symbol, result["total_records"])

    # 关闭批量模式并统一提交本只股票的写入
    set_batch_mode(False)
    try:
        get_global_connection().commit()
    except Exception:
        pass
    return result


class ScannerScheduler:
    """扫描调度器：管理多股票、多模式的扫描任务"""

    def __init__(
        self,
        tickers: List[str],
        start: str = "2023-01-01",
        end: Optional[str] = None,
        mode: str = "incremental",
        min_amplitude: float = 0.08,
        lookback: int = 5,
        verbose: bool = True,
    ):
        self.tickers = tickers
        self.start = start
        self.end = end
        self.mode = mode
        self.min_amplitude = min_amplitude
        self.lookback = lookback
        setup_logging(verbose)

    def run_once(self) -> dict:
        """执行一轮扫描：遍历所有配置股票，单只失败不中断整轮"""
        logger.info("\n🚀 调度器启动一轮扫描（%d 只股票，模式=%s）", len(self.tickers), self.mode)
        results = {}
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


def main():
    parser = argparse.ArgumentParser(description="股票形态扫描调度器")
    parser.add_argument("--tickers", default=None,
                        help="股票代码，逗号分隔；默认使用 config.SCAN_TICKERS（20只通信板块）")
    parser.add_argument("--start", default="2023-01-01", help="数据起始日期（默认 2023-01-01）")
    parser.add_argument("--end", default=None, help="数据结束日期（默认今天）")
    parser.add_argument("--mode", default="incremental", choices=["full", "incremental"],
                        help="full=全量 / incremental=增量（默认）")
    parser.add_argument("--interval", type=float, default=0,
                        help="定时循环间隔（小时），0=只跑一轮（默认）")
    parser.add_argument("--min-amplitude", type=float, default=0.08, help="波段最小振幅")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = list(SCAN_TICKERS)
        logger.info("📌 未指定 --tickers，使用 config.SCAN_TICKERS（%d 只）", len(tickers))
    sched = ScannerScheduler(
        tickers=tickers,
        start=args.start,
        end=args.end,
        mode=args.mode,
        min_amplitude=args.min_amplitude,
    )
    if args.interval and args.interval > 0:
        sched.run_loop(args.interval)
    else:
        sched.run_once()


if __name__ == "__main__":
    main()
