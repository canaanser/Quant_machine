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
                strength=r.get('strength'),
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


def _stage_worker(args):
    """暂存 worker（2026-08-28 小二陈，老板方案）：
    在独立暂存库中完整扫描一只股票（识别+写库+回填），零锁竞争。
    返回 (symbol, 暂存库路径, result)；失败返回 (symbol, None, {error})"""
    import os as _os
    symbol, start, end, mode, min_amplitude, lookback, stage_dir = args

    # 该 worker 进程内把数据库路径指向独立暂存库
    from structure_engine.scanner.data_writer import connection as _conn
    tmp_db = Path(stage_dir) / f"stage_{_os.getpid()}_{symbol}.db"
    for suffix in ('-wal', '-shm', '-journal'):
        f = Path(str(tmp_db) + suffix)
        if f.exists():
            try:
                f.unlink()
            except Exception:
                pass
    _conn.DB_PATH = tmp_db
    _conn._global_conn = None

    try:
        res = scan_symbol(symbol, start=start, end=end, mode=mode,
                          min_amplitude=min_amplitude, lookback=lookback)
        try:
            close_global_connection()
        except Exception:
            pass
        return (symbol, str(tmp_db), res)
    except Exception as e:
        try:
            close_global_connection()
        except Exception:
            pass
        return (symbol, None, {"symbol": symbol, "error": f"暂存异常: {e}"})


def _merge_stage(tmp_db, res):
    """主进程合并暂存库 → 主库（2026-08-28 小二陈）：
    ATTACH + INSERT OR REPLACE（显式列名，防 ALTER 列序错位），先提交数据再 DETACH，成功后才删暂存库"""
    from structure_engine.scanner.data_writer import get_global_connection, _init_tables
    _init_tables()   # 确保主库表存在（否则未限定表名会被 SQLite 解析到 stage 库）
    conn = get_global_connection()
    conn.commit()
    cur = conn.cursor()
    success = False
    try:
        cur.execute("ATTACH DATABASE ? AS stage", (str(tmp_db),))
        for table in ("pattern_history", "wave_history", "atomic_features", "scan_progress"):
            cols = ", ".join(c[1] for c in cur.execute(f"PRAGMA table_info({table})").fetchall())
            cur.execute(f"INSERT OR REPLACE INTO main.{table} ({cols}) SELECT {cols} FROM stage.{table}")
        conn.commit()          # ① 先提交合并数据（否则 DETACH 会被未提交事务锁住）
        cur.execute("DETACH DATABASE stage")
        conn.commit()          # ② 提交分离
        success = True
        res = dict(res or {})
        res["total_records"] = get_pattern_history_count(res.get("symbol"))
        logger.info("  ✅ 合并 %s 完成（pattern 累计 %d 条）", res.get("symbol"), res["total_records"])
    finally:
        if success:
            for suffix in ('', '-wal', '-shm', '-journal'):
                f = Path(str(tmp_db) + suffix)
                try:
                    if f.exists():
                        f.unlink()
                except Exception:
                    pass
        else:
            logger.warning("  ⚠️ 合并失败，暂存库保留: %s（可重扫该股恢复）", tmp_db)
    return res


def _merge_stages(tmp_dbs, results_by_symbol):
    """批量合并多个暂存库 → 主库（攒批合并，2026-08-28 小二陈）。
    注意：SQLite ATTACH 上限 10 个 → 内部按 8 个一组分批 ATTACH+INSERT+DETACH。
    修复（2026-08-28）：合并必须用【显式列名】——主库是 ALTER 加列（strength 在末尾），
    暂存库是新建（strength 在中间），SELECT * 按位置复制会列错位（created_at 被写进 strength）。"""
    from structure_engine.scanner.data_writer import get_global_connection, _init_tables
    _init_tables()   # 确保主库表存在（否则未限定表名会被 SQLite 解析到 stage 库）
    conn = get_global_connection()
    conn.commit()
    cur = conn.cursor()

    def table_cols(t):
        return ", ".join(c[1] for c in cur.execute(f"PRAGMA table_info({t})").fetchall())

    CHUNK = 8        # SQLite ATTACH 上限 10，留余量
    success_all = True
    for start in range(0, len(tmp_dbs), CHUNK):
        chunk = tmp_dbs[start:start + CHUNK]
        attached = []
        ok = False
        try:
            for i, tmp_db in enumerate(chunk):
                cur.execute(f"ATTACH DATABASE ? AS stage_{i}", (str(tmp_db),))
                attached.append(i)
            for table in ("pattern_history", "wave_history", "atomic_features", "scan_progress"):
                cols = table_cols(table)
                for i in attached:
                    cur.execute(
                        f"INSERT OR REPLACE INTO main.{table} ({cols}) SELECT {cols} FROM stage_{i}.{table}")
            conn.commit()          # ① 先提交合并数据（否则 DETACH 会被未提交事务锁住）
            for i in attached:
                cur.execute(f"DETACH DATABASE stage_{i}")
            conn.commit()          # ② 提交分离
            ok = True
        except Exception as e:
            success_all = False
            logger.error("  ❌ 合并分组(%d个)失败: %s", len(chunk), e)
            try:
                for i in attached:
                    cur.execute(f"DETACH DATABASE stage_{i}")
                conn.commit()
            except Exception:
                pass
        finally:
            if ok:
                for tmp_db in chunk:
                    for suffix in ('', '-wal', '-shm', '-journal'):
                        f = Path(str(tmp_db) + suffix)
                        try:
                            if f.exists():
                                f.unlink()
                        except Exception:
                            pass
    if success_all:
        for tmp_db in tmp_dbs:
            sym = Path(tmp_db).stem.split('_', 2)[-1]   # stage_{pid}_{symbol}.db
            res = results_by_symbol.get(sym)
            if res is not None:
                res["total_records"] = get_pattern_history_count(sym)
        logger.info("  ✅ 批量合并 %d 个暂存库完成", len(tmp_dbs))
    else:
        logger.warning("  ⚠️ 批量合并部分失败，失败组暂存库保留（可重扫恢复）")


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
        merge_batch: int = 50,
    ):
        self.tickers = tickers
        self.start = start
        self.end = end
        self.mode = mode
        self.min_amplitude = min_amplitude
        self.lookback = lookback
        self.workers = max(1, int(workers))
        self.merge_batch = max(1, int(merge_batch))
        setup_logging(verbose)

    def run_once(self) -> dict:
        """执行一轮扫描：遍历所有配置股票，单只失败不中断整轮。
        workers>1 时：worker 在独立暂存库完整扫描（识别+写库并行），主进程最后合并（老板方案 2026-08-28）"""
        logger.info("\n🚀 调度器启动一轮扫描（%d 只股票，模式=%s，workers=%d）",
                    len(self.tickers), self.mode, self.workers)
        results = {}
        if self.workers > 1 and len(self.tickers) > 1:
            from multiprocessing import Pool
            from config.config import PROJECT_ROOT
            stage_dir = PROJECT_ROOT / "data" / "index_store" / "stage"
            stage_dir.mkdir(parents=True, exist_ok=True)
            # 清空上次残留暂存库（重扫会重新生成；避免越积越多）
            try:
                for f in stage_dir.glob("stage_*.db*"):
                    try:
                        f.unlink()
                    except Exception:
                        pass
            except Exception:
                pass
            tasks = [(s, self.start, self.end, self.mode, self.min_amplitude, self.lookback, str(stage_dir))
                     for s in self.tickers]
            with Pool(processes=self.workers) as pool:
                pending = []   # [(tmp_db, res)]

                def flush():
                    nonlocal pending
                    if not pending:
                        return
                    dbs = [p[0] for p in pending]
                    for _, res in pending:
                        if res.get('symbol'):
                            results[res['symbol']] = res
                    try:
                        _merge_stages(dbs, results)
                    except Exception as e:
                        logger.error("  ❌ 批量合并异常: %s\n%s", e, traceback.format_exc())
                        for _, res in pending:
                            if res.get('symbol'):
                                results[res['symbol']] = {"symbol": res['symbol'], "error": str(e)}
                    pending = []

                for symbol, tmp_db, res in pool.imap_unordered(_stage_worker, tasks):
                    if res is None or res.get("error") or not tmp_db:
                        err = (res or {}).get("error", "暂存返回空")
                        logger.error("  ❌ %s 暂存失败: %s", symbol, err)
                        results[symbol] = {"symbol": symbol, "error": err}
                        continue
                    pending.append((tmp_db, res))
                    if len(pending) >= self.merge_batch:
                        flush()
                flush()   # 收尾剩余
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
    parser.add_argument("--pool", default="main", choices=["main", "ai", "all"],
                        help="扫描池：main=84只主池（默认）/ ai=20只AI龙头 / all=全市场(stock_list.txt)")
    parser.add_argument("--merge-batch", type=int, default=50,
                        help="攒批合并暂存库数量（默认50；4000只大池可调大）")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.strip().zfill(6) for t in args.tickers.split(",") if t.strip()]
    elif args.pool == "ai":
        from config.config import SCAN_TICKERS_AI
        tickers = list(SCAN_TICKERS_AI)
        logger.info("📌 --pool ai：AI 算力链龙头池（%d 只）", len(tickers))
    elif args.pool == "all":
        from config.config import PROJECT_ROOT
        lst = PROJECT_ROOT / "data" / "stock_list.txt"
        if lst.exists():
            tickers = [l.strip() for l in lst.read_text(encoding="utf-8").splitlines() if l.strip()]
            logger.info("📌 --pool all：全市场 %d 只（stock_list.txt）", len(tickers))
        else:
            logger.error("❌ data/stock_list.txt 不存在，先跑 scripts/dump_stock_list.py")
            return
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
        merge_batch=args.merge_batch,
    )
    if args.interval and args.interval > 0:
        sched.run_loop(args.interval)
    else:
        sched.run_once()


if __name__ == "__main__":
    main()
