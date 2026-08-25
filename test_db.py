"""
测试 freestockdb 连接和历史数据恢复情况
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from stock_sdk import rd, init
from core.data_loader import load_data


def test_db():
    print("=" * 60)
    print("  测试 freestockdb 数据恢复状态")
    print("=" * 60)

    # 1. 测试连接
    print("\n[1] 测试连接...")
    try:
        init("127.0.0.1", 7899)
        print("✅ 连接成功")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return

    # 2. 测试单日数据（2025-08-11，之前是空的）
    print("\n[2] 测试单日数据 (2025-08-11)...")
    try:
        result = rd.get("日k:000063:20250811")
        if result and result != []:
            print(f"✅ 有数据: {result}")
        else:
            print("❌ 仍无数据")
    except Exception as e:
        print(f"❌ 查询失败: {e}")

    # 3. 测试区间数据（2025-01-01 ~ 2026-08-11）
    print("\n[3] 测试区间数据 (2025-01-01 ~ 2026-08-11)...")
    try:
        market_data = load_data(
            source='freestockdb',
            tickers=['000063'],
            start='2025-01-01',
            end='2026-08-11',
            frequency='1d',
            fq='qfq'
        )
        if market_data and not market_data.price.empty:
            print(f"✅ 加载成功: {len(market_data.price)} 个交易日")
            print(f"   日期范围: {market_data.price.index.min()} 至 {market_data.price.index.max()}")
        else:
            print("❌ 仍无区间数据")
    except Exception as e:
        print(f"❌ 加载失败: {e}")

    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_db()