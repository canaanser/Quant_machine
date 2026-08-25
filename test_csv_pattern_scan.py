"""
本地 CSV 形态扫描测试
直接读取根目录下的 中兴通讯_2025_2026.csv 进行形态扫描
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from structure_engine.scanner import scan_patterns
from structure_engine.schemas import StateTable


def main():
    print("=" * 60)
    print("  本地 CSV 形态扫描测试 — 中兴通讯")
    print("=" * 60)

    # 1. 读取本地 CSV
    print("\n[1] 读取本地 CSV...")
    df = pd.read_csv("中兴通讯_2025_2026.csv")

    # 列名映射
    column_mapping = {
        '日期/时间': 'date',
        '开盘价': 'open',
        '最高价': 'high',
        '最低价': 'low',
        '收盘价': 'close',
        '成交量': 'volume',
    }
    df.rename(columns=column_mapping, inplace=True)

    # 日期处理
    df['date'] = pd.to_datetime(df['date'].astype(str), format='%Y%m%d')
    df = df.set_index('date')
    df = df.sort_index()

    # 只保留 OHLCV
    ohlc = df[['open', 'high', 'low', 'close', 'volume']].copy()
    print(f"   数据条数: {len(ohlc)}")
    print(f"   日期范围: {ohlc.index.min()} 至 {ohlc.index.max()}")

    # 2. 运行形态扫描
    print("\n[2] 运行形态扫描...")
    results = scan_patterns(ohlc)

    print(f"   ✅ 扫描完成: 匹配到 {len(results)} 个形态\n")

    # 3. 输出结果
    print("3. 匹配结果（前 20 条）:")
    print("-" * 60)
    for i, r in enumerate(results[:20]):
        date_str = r['date'].strftime('%Y-%m-%d') if hasattr(r['date'], 'strftime') else str(r['date'])[:10]
        print(f"   {i+1:2d}. {date_str}  {r['pattern_type']:15}  {r['category']:8}  强度: {r['strength']:.3f}")

    if len(results) > 20:
        print(f"   ... 还有 {len(results) - 20} 条")

    # 4. 形态分布统计
    print("\n4. 形态分布统计:")
    print("-" * 60)
    from collections import Counter
    pattern_counts = Counter([r['pattern_type'] for r in results])
    for pattern, count in pattern_counts.most_common():
        print(f"   {pattern:20} : {count} 次")

    # 5. 测试 StateTable 转换
    print("\n5. 测试 StateTable 转换:")
    print("-" * 60)
    if results:
        sample = results[0]
        state = StateTable(
            date=sample['date'].strftime('%Y-%m-%d') if hasattr(sample['date'], 'strftime') else str(sample['date']),
            symbol="000063",
            pattern_ids=[sample['pattern_id']],
            pattern_type=sample['pattern_type'],
            category=sample['category'],
            strength=sample['strength'],
            meta=sample['meta']
        )
        print(f"   StateTable 转换成功:")
        print(f"   日期: {state.date}")
        print(f"   形态: {state.pattern_type}")
        print(f"   类别: {state.category}")
        print(f"   强度: {state.strength}")
        print(f"   ✅ StateTable 验证通过")

    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()