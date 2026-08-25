"""
测试全链路：滑动窗口波段探测 → 形态扫描 → 位置映射回写 → 波段写入 → pending回填（支持全量/增量）
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
from structure_engine.scanner.position_mapper import map_position, backfill_band_positions
from structure_engine.scanner.data_writer import (
    get_pattern_history_count,
    update_scan_progress,
    get_last_scan_progress,
    DB_PATH,
    close_global_connection,
    get_global_connection,
    get_pending_records_in_range,
    update_band_position,
    write_wave_history
)

# ===== 调试开关 =====
debug = False


def test_full_pipeline(mode: str = "incremental", window_days: int = 150, step: int = 100):
    """
    全链路测试，支持全量和增量两种模式

    参数：
        mode: "full" 全量扫描 / "incremental" 增量扫描（默认）
        window_days: 滑动窗口大小（默认150天）
        step: 滑动步长（默认100天）
    """
    print("=" * 60)
    print(f"测试全链路：滑动窗口波段探测 → 形态扫描 → 位置映射回写 → pending回填（模式：{mode}）")
    print("=" * 60)

    # 1. 加载数据
    print("\n[1] 加载数据...")
    market_data = load_data(
        source='freestockdb',
        tickers=['000063'],
        start='2016-01-01',
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

    # ===== 3. 滑动窗口遍历全部历史数据 =====
    print(f"\n[3] 滑动窗口扫描（窗口={window_days}天，步长={step}天）...")
    total_days = len(ohlc)
    all_waves = []          # 收集所有窗口识别的波段
    all_results = []        # 收集所有窗口的形态匹配结果

    for start_idx in range(0, total_days - window_days + 1, step):
        end_idx = min(start_idx + window_days, total_days)
        window_df = ohlc.iloc[start_idx:end_idx]

        if len(window_df) < 20:
            continue

        # 识别波段
        waves = detect_waves(
            df=window_df,
            window_days=window_days,
            lookback=5,
            min_amplitude=0.08
        )

        if not waves:
            continue

        # ===== 处理每个波段 =====
        for wave in waves:
            # 收集到全局列表
            all_waves.append(wave)

            # 写入波段历史表
            try:
                write_wave_history(symbol, wave, scan_version=1)
            except Exception as e:
                if debug:
                    print(f"   ⚠️ 写入波段失败: {e}")

        # ===== 扫描形态（按波段） =====
        for wave in waves:
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
    # ===== 【在这里插入下方代码】 =====
    # 补扫：对可能被滑动窗口遗漏的下跌段单独识别
    print("\n[补扫] 单独识别下跌段波段...")
    debug_df = ohlc.loc['2026-05-01':'2026-08-19']
    debug_waves = detect_waves(debug_df, window_days=150, lookback=5, min_amplitude=0.08)
    for w in debug_waves:
        # 检查是否已在 all_waves 中
        exists = False
        for existing in all_waves:
            if existing.get('peak_date') == w.get('peak_date') and existing.get('valley_date') == w.get('valley_date'):
                exists = True
                break
        if not exists:
            all_waves.append(w)
            try:
                write_wave_history(symbol, w, scan_version=1)
                print(f"  ✅ 补充写入波段: {w.get('peak_date')} → {w.get('valley_date')}")
            except Exception as e:
                if debug:
                    print(f"  ⚠️ 写入失败: {e}")
    print("  [补扫] 完成")
    # ===== 插入结束 =====
    # ===== 4. 位置映射回写（计算精确 band_position） =====
    print("\n[4] 位置映射回写（计算精确 band_position）...")
    update_count = 0
    fail_count = 0
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    for r in all_results:
        match_date = r['date']
        try:
            if match_date in ohlc.index:
                match_price = ohlc.loc[match_date, 'close']
            else:
                match_date_dt = pd.to_datetime(match_date)
                if match_date_dt in ohlc.index:
                    match_price = ohlc.loc[match_date_dt, 'close']
                else:
                    continue

            pos_info = map_position(match_date, match_price, all_waves)

            if hasattr(match_date, 'strftime'):
                match_date_str = match_date.strftime('%Y-%m-%d')
            else:
                match_date_str = str(match_date)[:10]

            cursor.execute("""
                SELECT record_id FROM pattern_history
                WHERE symbol = ? AND pattern_id = ? AND match_date LIKE ?
            """, (
                symbol,
                r['pattern_id'],
                f"{match_date_str}%"
            ))
            row = cursor.fetchone()
            if row:
                record_id = row[0]
                cursor.execute("""
                    UPDATE pattern_history
                    SET band_position = ?, band_progress = ?, band_direction = ?
                    WHERE record_id = ?
                """, (
                    pos_info['band_position'],
                    pos_info['band_progress'],
                    pos_info['band_direction'],
                    record_id
                ))
                update_count += cursor.rowcount
            else:
                fail_count += 1

        except Exception as e:
            print(f"      ⚠️ 位置映射失败: {match_date} | {e}")
            fail_count += 1

    conn.commit()
    conn.close()
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

    print("\n" + "=" * 60)
    print("✅ 全链路测试完成")
    print("=" * 60)


if __name__ == "__main__":
    # 默认使用增量模式
    # 第一次运行用 mode="full"，之后用 mode="incremental"
    test_full_pipeline(mode="full", window_days=150, step=100)