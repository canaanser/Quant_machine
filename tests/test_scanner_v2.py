"""
测试全链路：波段探测 → 形态扫描 → 位置映射回写 → 波段写入 → pending回填（支持全量/增量）

修复说明（2026-08-26 小二陈）：
  原滑动窗口法（window=150, step=100）存在覆盖空洞——
  range(0, total-window+1, step) 的最后一个窗口截断后，数据尾部约 60 个交易日
  不在任何窗口内，导致 5 月之后的波段/形态整体漏报（长上影线断点根因）。
  改为全量 detect_waves 一次识别：无遗漏、无重复（同时消除重复写入）。
"""

import sys
import sqlite3
from pathlib import Path

# ===== 把项目根目录加入 Python 路径 =====
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from core.data_loader import load_data
from structure_engine.scanner.wave_detector import detect_waves
from structure_engine.scanner.pattern_scanner import scan_patterns
from structure_engine.scanner.position_mapper import (
    map_position, backfill_band_positions, backfill_positions_for_results,
)
from structure_engine.scanner.data_writer import (
    get_pattern_history_count,
    update_scan_progress,
    get_last_scan_progress,
    DB_PATH,
    close_global_connection,
    get_global_connection,
    get_pending_records_in_range,
    update_band_position,
    write_wave_history,
    set_batch_mode,
)

# ===== 调试开关 =====
debug = False


def test_full_pipeline(mode: str = "incremental", window_days: int = 150, step: int = 100):
    """
    全链路测试，支持全量和增量两种模式

    参数：
        mode: "full" 全量扫描 / "incremental" 增量扫描（默认）
        window_days: 兼容参数（保留，全量识别时取全部数据）
        step: 兼容参数（保留，不再使用）
    """
    print("=" * 60)
    print(f"测试全链路：波段探测 → 形态扫描 → 位置映射回写 → pending回填（模式：{mode}）")
    print("=" * 60)
    set_batch_mode(True)  # 批量写入模式（性能优化）

    # 1. 加载数据
    print("\n[1] 加载数据...")
    market_data = load_data(
        source='freestockdb',
        tickers=['000063'],
        start='2023-01-01',
        end="2027-01-01"
    )
    symbol = '000063'
    ohlc = market_data.get_ohlc(symbol)
    print(f"    ✅ 加载 {len(ohlc)} 个交易日")

    # ===== 2. 检查扫描进度（增量模式） =====
    print("\n[2] 检查扫描进度...")
    if mode == "incremental":
        progress = get_last_scan_progress(symbol)
        if progress:
            last_date = progress['last_scanned_date']
            print(f"    📌 上次扫描到: {last_date}")
            if last_date in ohlc.index:
                ohlc = ohlc.loc[last_date:]
            else:
                ohlc = ohlc[ohlc.index >= last_date]
            print(f"    📌 本次扫描新增 {len(ohlc)} 个交易日")
        else:
            print("    📌 未找到扫描进度，执行全量扫描")
    else:
        print("    📌 全量模式，扫描全部数据")

    if len(ohlc) < 5:
        print("    ⚠️ 新增数据不足5天，跳过扫描")
        return

    # ===== 3. 全量波段识别（一次识别全部，避免滑动窗口覆盖空洞） =====
    print(f"\n[3] 全量波段识别（window_days={len(ohlc)}）...")
    all_waves = detect_waves(
        df=ohlc,
        window_days=len(ohlc),
        lookback=5,
        min_amplitude=0.08
    )
    all_results = []

    # 写入波段历史表
    for wave in all_waves:
        try:
            write_wave_history(symbol, wave, scan_version=1)
        except Exception as e:
            if debug:
                print(f"   ⚠️ 写入波段失败: {e}")

    # ===== 扫描每个波段的形态 =====
    for wave in all_waves:
        peak_date = wave.get('peak_date')
        valley_date = wave.get('valley_date')

        if not peak_date or not valley_date:
            continue

        start_date = peak_date if wave.get('direction') == 'down' else valley_date
        end_date = valley_date if wave.get('direction') == 'down' else peak_date
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        # 截取波段片段（右窗延伸20日）
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

        # 扫描形态
        results = scan_patterns(
            df=wave_df,
            debug=False,
            write_to_db=True,
            symbol=symbol,
            peak_date=wave['peak_date'],
            valley_date=wave['valley_date'],
            band_position=None
        )

        for r in results:
            r['_wave'] = wave
            all_results.append(r)

    print(f"    ✅ 识别到 {len(all_waves)} 个波段，匹配到 {len(all_results)} 个形态")

    # ===== 4. 位置映射回写（计算精确 band_position） =====
    print("\n[4] 位置映射回写（计算精确 band_position，公共函数）...")
    update_count, fail_count = backfill_positions_for_results(
        symbol, all_results, ohlc, all_waves
    )
    print(f"    ✅ 更新了 {update_count} 条记录的 band_position")
    if fail_count > 0:
        print(f"    ⚠️ {fail_count} 条记录未匹配到")

    # ===== 4.5 pending 回填（将确认位置的记录标记为 ready） =====
    print("\n[4.5] pending 回填（标记 ready）...")
    backfill_total = 0
    for wave in all_waves:
        try:
            count = backfill_band_positions(symbol, wave, ohlc, sys.modules[__name__])
            backfill_total += count
            if count > 0 and debug:
                print(f"    ✅ 波段 {wave.get('peak_date')}~{wave.get('valley_date')} 回填 {count} 条")
        except Exception as e:
            if debug:
                print(f"    ⚠️ 回填失败: {e}")
    print(f"    ✅ 共回填 {backfill_total} 条记录为 ready")

    # ===== 5. 更新扫描进度 =====
    if mode == "incremental" and len(ohlc) > 0:
        print("\n[5] 更新扫描进度...")
        last_date = ohlc.index[-1]
        if hasattr(last_date, 'strftime'):
            last_date_str = last_date.strftime('%Y-%m-%d')
        else:
            last_date_str = str(last_date)
        update_scan_progress(
            symbol=symbol,
            last_scanned_date=last_date_str,
            last_window_start=last_date_str,
            scan_mode=mode,
            scan_version=1
        )
        print(f"    ✅ 扫描进度已更新到: {last_date_str}")

    # ===== 6. 验证数据库写入 =====
    print("\n[6] 验证数据库写入...")
    count = get_pattern_history_count(symbol)
    print(f"    ✅ pattern_history 中 {symbol} 的记录数: {count}")

    # ===== 7. 查看最新一条记录 =====
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pattern_name, match_date, peak_date, valley_date, band_position, band_progress, return_5d, return_10d, return_20d
        FROM pattern_history 
        WHERE symbol = ? 
        ORDER BY created_at DESC 
        LIMIT 1
    """, (symbol,))
    row = cursor.fetchone()
    conn.close()
    if row:
        print(f"    ✅ 最新记录: {row[0]} | match={row[1]} | peak={row[2]} | valley={row[3]} | 位置={row[4]} | 进度={row[5] if row[5] is not None else 0.0:.2f} | 5d={row[6]} | 10d={row[7]} | 20d={row[8]}")

    close_global_connection()
    set_batch_mode(False)

    print("\n" + "=" * 60)
    print("✅ 全链路测试完成")
    print("=" * 60)


if __name__ == "__main__":
    # 默认使用增量模式
    # 第一次运行用 mode="full"，之后用 mode="incremental"
    test_full_pipeline(mode="full", window_days=150, step=100)
