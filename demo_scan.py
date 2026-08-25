"""
形态扫描演示 — 使用 freestockdb 真实数据
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from core.data_loader import load_data
from structure_engine.scanner import scan_patterns
from datetime import datetime


def main():
    print("=" * 60)
    print("  形态扫描演示 (freestockdb)")
    print("=" * 60)

    # 使用 freestockdb 加载中兴通讯 2025-01-01 至今的数据
    market_data = load_data(
        source='freestockdb',
        tickers=['000063'],
        start='2025-01-01',
        end=datetime.now().strftime("%Y-%m-%d"),
        frequency="1d",
        fq="qfq"
    )

    print(f"✅ 数据加载: {len(market_data.price)} 个交易日")

    # 获取 OHLCV
    df = market_data.get_ohlc('000063')
    print(f"   OHLCV 形状: {df.shape}")

    # 运行形态扫描
    results = scan_patterns(df)

    print(f"\n✅ 匹配到 {len(results)} 个形态\n")

    for r in results[:10]:
        print(f"  {r['date']}  {r['pattern_type']} (强度: {r['strength']:.3f})")


if __name__ == "__main__":
    main()