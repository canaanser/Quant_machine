import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from datetime import datetime, timedelta
from core.data_loader import load_data
from structure_engine.morphology.atomic import (
    BodyRatio,
    ShadowRatio,
    GapDetector,
    EngulfingDetector,
    InsideDetector,
    ConsecutiveBars,
    VolumeSpike,
)


def test_atom(atom, klines, name):
    matched = 0
    strengths = []
    for i in range(len(klines)):
        try:
            result = atom.check(klines, i, {})
            if result['matched']:
                matched += 1
                strengths.append(result['strength'])
        except Exception:
            pass
    avg_strength = sum(strengths) / len(strengths) if strengths else 0
    print(f"   {name:20} : 匹配 {matched:4} 次, 平均强度: {avg_strength:.3f}")


def main():
    print("=" * 60)
    print("  原子特征调试")
    print("=" * 60)

    # 加载真实数据
    print("\n1. 加载数据...")
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

    market_data = load_data(
        source='freestockdb',
        tickers=['000063'],
        start=start_date,
        end=end_date,
        frequency="1d",
        fq="qfq"
    )

    # 使用 get_ohlc 获取完整 OHLCV
    ohlc = market_data.get_ohlc('000063')
    print(f"   OHLCV 形状: {ohlc.shape}")

    klines = []
    for idx, row in ohlc.iterrows():
        klines.append({
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': row['volume'],
        })

    print(f"   K线数量: {len(klines)}\n")

    # 逐个测试原子
    print("2. 原子匹配统计:")
    print("-" * 50)

    test_atom(BodyRatio(min_ratio=0.25, max_ratio=0.65), klines, "BodyRatio")
    test_atom(ShadowRatio(shadow_type="lower", min_ratio=2.5), klines, "ShadowRatio(lower)")
    test_atom(ShadowRatio(shadow_type="upper", min_ratio=2.5), klines, "ShadowRatio(upper)")
    test_atom(GapDetector(gap_type="up", min_gap_ratio=0.01), klines, "GapDetector(up)")
    test_atom(GapDetector(gap_type="down", min_gap_ratio=0.01), klines, "GapDetector(down)")
    test_atom(EngulfingDetector(engulfing_type="bullish"), klines, "Engulfing(bullish)")
    test_atom(EngulfingDetector(engulfing_type="bearish"), klines, "Engulfing(bearish)")
    test_atom(InsideDetector(), klines, "InsideDetector")
    test_atom(ConsecutiveBars(direction="up", count=3), klines, "ConsecutiveBars(up)")
    test_atom(ConsecutiveBars(direction="down", count=3), klines, "ConsecutiveBars(down)")
    test_atom(VolumeSpike(lookback=5, multiplier=1.8), klines, "VolumeSpike")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()