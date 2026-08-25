"""
验证 backfill_band_positions 回填逻辑
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import sqlite3
from core.data_loader import load_data
from structure_engine.scanner.wave_detector import detect_waves
from structure_engine.scanner.position_mapper import map_position
from structure_engine.scanner.data_writer import (
    DB_PATH,
    get_global_connection,
    close_global_connection,
    get_pending_records_in_range,
    update_band_position
)


def test_backfill():
    print("=" * 60)
    print("验证 backfill_band_positions 回填逻辑")
    print("=" * 60)

    symbol = '000063'

    # 1. 加载数据
    print("\n[1] 加载数据...")
    market_data = load_data(
        source='freestockdb',
        tickers=[symbol],
        start='2025-01-01',
        end='2026-08-11'
    )
    ohlc = market_data.get_ohlc(symbol)
    print(f"    ✅ 加载 {len(ohlc)} 个交易日")

    # 2. 识别波段
    print("\n[2] 运行波段探测器...")
    waves = detect_waves(
        df=ohlc,
        window_days=150,
        lookback=5,
        min_amplitude=0.08
    )
    print(f"    ✅ 识别到 {len(waves)} 个波段")

    # 3. 查看回填前的状态
    print("\n[3] 回填前状态...")
    conn = get_global_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM pattern_history WHERE symbol = ?", (symbol,))
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM pattern_history WHERE symbol = ? AND band_position_ready = 1", (symbol,))
    ready_before = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM pattern_history WHERE symbol = ? AND band_position_ready = 0", (symbol,))
    pending_before = cursor.fetchone()[0]

    print(f"    总记录数: {total}")
    print(f"    ready (1): {ready_before}")
    print(f"    pending (0): {pending_before}")

    # 4. 执行回填
    print("\n[4] 执行回填...")
    total_updated = 0

    for i, wave in enumerate(waves):
        peak_date = wave.get('peak_date')
        valley_date = wave.get('valley_date')
        if not peak_date or not valley_date:
            continue

        if wave.get('direction') == 'down':
            start_date, end_date = valley_date, peak_date
        else:
            start_date, end_date = peak_date, valley_date

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        pending = get_pending_records_in_range(symbol, start_date, end_date)
        if not pending:
            continue

        print(f"    波段 {i+1}: {start_date} → {end_date}, pending 记录 {len(pending)} 条")

        for record in pending:
            match_date = record['match_date']
            match_price = record['match_price']

            if match_date in ohlc.index:
                match_price = ohlc.loc[match_date, 'close']

            pos_info = map_position(match_date, match_price, waves)

            if pos_info['band_position'] == 'unknown':
                continue

            result = update_band_position(
                record_id=record['record_id'],
                band_position=pos_info['band_position'],
                band_progress=pos_info['band_progress'],
                band_direction=pos_info['band_direction']
            )
            total_updated += result

    # 注意：这里不要关闭连接，因为后面还要用
    # 但 update_band_position 内部会 commit，不影响当前连接
    print(f"\n    ✅ 共回填 {total_updated} 条记录")

    # ===== 重新获取连接进行统计（避免使用已关闭的连接） =====
    # 先关闭之前的连接，再重新打开
    close_global_connection()

    print("\n[5] 回填后状态...")
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM pattern_history WHERE symbol = ? AND band_position_ready = 1", (symbol,))
    ready_after = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM pattern_history WHERE symbol = ? AND band_position_ready = 0", (symbol,))
    pending_after = cursor.fetchone()[0]

    print(f"    ready (1): {ready_after}")
    print(f"    pending (0): {pending_after}")
    print(f"    变化: +{ready_after - ready_before}")

    # 6. 验证分布
    print("\n[6] band_position 分布（ready 记录）...")
    cursor.execute("""
        SELECT band_position, COUNT(*) 
        FROM pattern_history 
        WHERE symbol = ? AND band_position_ready = 1
        GROUP BY band_position
        ORDER BY COUNT(*) DESC
    """, (symbol,))
    rows = cursor.fetchall()
    for row in rows:
        print(f"    {row[0]}: {row[1]} 条")

    cursor.execute("""
        SELECT COUNT(*) 
        FROM pattern_history 
        WHERE symbol = ? AND band_position_ready = 0
    """, (symbol,))
    pending_remaining = cursor.fetchone()[0]
    if pending_remaining > 0:
        print(f"    ⚠️ 仍有 {pending_remaining} 条 pending 记录（位置未知）")

    conn.close()
    close_global_connection()

    print("\n" + "=" * 60)
    print("✅ 验证完成")
    print("=" * 60)


if __name__ == "__main__":
    test_backfill()