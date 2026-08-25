"""
真实数据形态扫描测试
从 free-stockdb 加载真实股票数据，运行形态扫描并输出结果
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from datetime import datetime, timedelta
from core.data_loader import load_data
from structure_engine.scanner import scan_patterns
from structure_engine.schemas import StateTable


def main():
    print("=" * 60)
    print("  真实数据形态扫描测试")
    print("=" * 60)

    # 1. 加载真实数据
    print("\n1. 加载数据...")
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

    try:
        market_data = load_data(
            source='freestockdb',
            tickers=['000063'],
            start=start_date,
            end=end_date,
            frequency="1d",
            fq="qfq"
        )
        price_df = market_data.price
        print(f"   ✅ 加载成功: {len(price_df)} 个交易日, {len(price_df.columns)} 只股票")
    except Exception as e:
        print(f"   ❌ 数据加载失败: {e}")
        return

    # 2. 运行形态扫描
    print("\n2. 运行形态扫描...")
    df = price_df.copy()
    # 重命名列为中文（scan_patterns 兼容中英文）
    if 'close' in df.columns:
        df.columns = ['收盘价' if c == 'close' else c for c in df.columns]
    results = scan_patterns(df)

    print(f"   ✅ 扫描完成: 匹配到 {len(results)} 个形态\n")

    # 3. 输出结果
    print("3. 匹配结果（前 20 条）:")
    print("-" * 60)
    for i, r in enumerate(results[:20]):
        date_str = r['date'].strftime('%Y-%m-%d') if hasattr(r['date'], 'strftime') else str(r['date'])[:10]
        print(f"   {i+1:2d}. {date_str}  {r['pattern_type']:12}  {r['category']:8}  强度: {r['strength']:.3f}")

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