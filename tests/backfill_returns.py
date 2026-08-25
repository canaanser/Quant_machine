"""
补算已回填 ready 记录的收益字段
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from core.data_loader import load_data
from structure_engine.scanner.score_calculator import calc_base_score, calc_composite_return
from structure_engine.scanner.data_writer import DB_PATH, get_global_connection, close_global_connection


def backfill_returns():
    print("=" * 60)
    print("补算 ready 记录的收益字段")
    print("=" * 60)

    # 1. 加载完整 OHLCV 数据
    symbol = '000063'
    market_data = load_data(
        source='freestockdb',
        tickers=[symbol],
        start='2016-01-01',
        end='2099-01-01'
    )
    ohlc = market_data.get_ohlc(symbol)
    print(f"    ✅ 加载 {len(ohlc)} 个交易日")

    # 2. 获取所有 ready 记录（band_position_ready=1 且 composite_return IS NULL）
    conn = get_global_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT record_id, match_date, match_price
        FROM pattern_history
        WHERE symbol = ? AND band_position_ready = 1 AND composite_return IS NULL
    """, (symbol,))

    records = cursor.fetchall()
    print(f"    📌 找到 {len(records)} 条待补算记录")

    if not records:
        print("    ✅ 没有需要补算的记录")
        close_global_connection()
        return

    # 3. 逐条补算
    updated = 0
    for record_id, match_date, match_price in records:
        # 找到匹配日期的索引
        if match_date not in ohlc.index:
            continue

        idx = ohlc.index.get_loc(match_date)

        # 计算 5/10/20 日收益率
        def get_return(days):
            if idx + days < len(ohlc):
                return (ohlc.iloc[idx + days]['close'] - match_price) / match_price
            return 0.0

        r5 = get_return(5)
        r10 = get_return(10)
        r20 = get_return(20)
        composite = calc_composite_return(r5, r10, r20)
        base_score = calc_base_score(composite)

        # 更新数据库
        cursor.execute("""
            UPDATE pattern_history
            SET return_5d = ?,
                return_10d = ?,
                return_20d = ?,
                composite_return = ?,
                base_score = ?,
                scan_version = 1
            WHERE record_id = ?
        """, (r5, r10, r20, composite, base_score, record_id))

        updated += cursor.rowcount

    conn.commit()
    close_global_connection()

    print(f"    ✅ 更新了 {updated} 条记录的收益字段")


if __name__ == "__main__":
    backfill_returns()