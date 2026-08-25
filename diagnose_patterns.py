"""
系统性形态诊断 — 找出为什么匹配为0
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from datetime import datetime
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
from structure_engine.morphology.registry import REGISTRY
from structure_engine.scanner.pattern_scanner import scan_patterns


def main():
    print("=" * 70)
    print("  系统性形态诊断 — 九安医疗 (002432)")
    print("=" * 70)

    # ---------- 1. 加载数据 ----------
    print("\n1. 加载数据...")
    market_data = load_data(
        source='freestockdb',
        tickers=['002432'],
        start="2021-01-01",
        end=datetime.now().strftime("%Y-%m-%d"),
        frequency="1d",
        fq="qfq"
    )

    ohlc = market_data.get_ohlc('002432')
    print(f"   OHLCV 形状: {ohlc.shape}")

    # 转成K线列表
    klines = []
    for idx, row in ohlc.iterrows():
        klines.append({
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': row['volume'],
        })

    print(f"   K线数量: {len(klines)}")

    # ---------- 2. 测试原子匹配 ----------
    print("\n2. 原子匹配率测试（每个原子独立匹配）:")
    print("-" * 70)

    atoms = [
        ("BodyRatio", BodyRatio(min_ratio=0.25, max_ratio=0.65)),
        ("ShadowRatio_lower", ShadowRatio(shadow_type="lower", min_ratio=2.5)),
        ("ShadowRatio_upper", ShadowRatio(shadow_type="upper", min_ratio=2.5)),
        ("GapDetector_up", GapDetector(gap_type="up", min_gap_ratio=0.01)),
        ("GapDetector_down", GapDetector(gap_type="down", min_gap_ratio=0.01)),
        ("Engulfing_bullish", EngulfingDetector(engulfing_type="bullish")),
        ("Engulfing_bearish", EngulfingDetector(engulfing_type="bearish")),
        ("InsideDetector", InsideDetector()),
        ("ConsecutiveBars_up", ConsecutiveBars(direction="up", count=3)),
        ("ConsecutiveBars_down", ConsecutiveBars(direction="down", count=3)),
        ("VolumeSpike", VolumeSpike(lookback=5, multiplier=1.8)),
    ]

    atom_stats = {}
    for name, atom in atoms:
        matched = 0
        total = len(klines)
        for i in range(len(klines)):
            try:
                result = atom.check(klines, i, {})
                if result.get('matched', False):
                    matched += 1
            except Exception:
                pass
        atom_stats[name] = matched
        print(f"   {name:20} : {matched:4} / {total} 次匹配")

    # ---------- 3. 测试组合形态（注册表） ----------
    print("\n3. 注册表形态匹配（组合逻辑）:")
    print("-" * 70)

    registry_patterns = REGISTRY.list_all()
    print(f"   注册表形态数量: {len(registry_patterns)}")
    for pat in registry_patterns:
        pattern_id = pat.get('id')
        human = pat.get('human_readable', pattern_id)
        atomics = pat.get('atomics', [])
        combine = pat.get('combine', 'and')
        print(f"   - {human} (combine={combine}, 原子数={len(atomics)})")

    # ---------- 4. 扫描器直接测试 ----------
    print("\n4. 扫描器测试:")
    print("-" * 70)

    # 临时降低阈值
    old_min = sys.modules['structure_engine.scanner.pattern_scanner'].MIN_STRENGTH_THRESHOLD
    sys.modules['structure_engine.scanner.pattern_scanner'].MIN_STRENGTH_THRESHOLD = 0.001

    results = scan_patterns(ohlc)
    print(f"   扫描结果: {len(results)} 个形态")

    # ---------- 5. 结论 ----------
    print("\n5. 结论:")
    print("-" * 70)

    if len(results) > 0:
        print(f"   ✅ 扫描器正常工作了，匹配到 {len(results)} 个形态")
    else:
        print("   ❌ 扫描器匹配为0")

        # 找出可能的原因
        max_atom_match = max(atom_stats.values()) if atom_stats else 0
        if max_atom_match == 0:
            print("   → 原因1: 原子本身没有匹配，检查OHLCV数据是否正确传递")
        else:
            print(f"   → 原因1: 原子有匹配（最高 {max_atom_match} 次），但组合形态要求多个原子同时成立")

        # 检查注册表
        if len(registry_patterns) == 0:
            print("   → 原因2: 注册表为空，没有形态定义")
        else:
            print(f"   → 原因2: 注册表有 {len(registry_patterns)} 个形态")

        # 检查是否有单原子形态
        has_single_atom = any(len(p.get('atomics', [])) == 1 for p in registry_patterns)
        if not has_single_atom:
            print("   → 原因3: 所有形态都是多原子组合（需要多个原子同时成立），建议增加单原子形态")
        else:
            print("   → 原因3: 已有单原子形态，但可能阈值或数据传递仍有问题")

    print("\n" + "=" * 70)
    print("  诊断完成")
    print("=" * 70)


if __name__ == "__main__":
    main()