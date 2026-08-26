# -*- coding: utf-8 -*-
"""
形态扫描单元测试（秒级，无数据依赖，纯构造 K 线）
2026-08-26 小二陈：验证核心原子特征 + scan_patterns 端到端
注意：原子 API 为 check(klines: list[dict], idx, context) -> {'value','is_valid','details'}
"""
import pandas as pd


def make_klines(rows):
    """构造 klines dict 列表：rows = [(open, high, low, close), ...]"""
    dates = pd.date_range('2026-01-01', periods=len(rows), freq='D')
    out = []
    for i, (o, h, l, c) in enumerate(rows):
        out.append({
            'date': dates[i].strftime('%Y-%m-%d'),
            'open': o, 'high': h, 'low': l, 'close': c,
            'volume': 1000000 + i * 1000,
        })
    return out


class TestAtomicFeatures:
    def test_body_ratio_normal(self):
        """实体占比：实体 0.2 / 振幅 0.7 ≈ 0.29 应在 [0.25, 0.65] 内"""
        from structure_engine.morphology.atomic.body_ratio import BodyRatio
        atom = BodyRatio(min_ratio=0.25, max_ratio=0.65)
        klines = make_klines([(10.0, 10.5, 9.8, 10.2)])
        res = atom.check(klines, 0, {})
        assert res['is_valid'] is True
        assert 0.2 < res['value'] < 0.5  # 实体占比约 0.29

    def test_long_upper_shadow(self):
        """长上影线：上影 1.8 / 实体 0.2 = 9 倍 ≥ 2.5 → 命中"""
        from structure_engine.morphology.atomic.shadow_ratio import ShadowRatio
        atom = ShadowRatio(shadow_type='upper', min_ratio=2.5)
        klines = make_klines([(10.0, 12.0, 9.9, 10.2)])
        res = atom.check(klines, 0, {})
        assert res['is_valid'] is True
        assert res['value'] >= 2.5

    def test_consecutive_bars(self):
        """连续 3 阳线应命中 count=3（value 已归一化，命中即 1.0）"""
        from structure_engine.morphology.atomic.consecutive_bars import ConsecutiveBars
        atom = ConsecutiveBars(direction='up', count=3)
        klines = make_klines([
            (10.0, 10.5, 9.9, 10.4),
            (10.4, 10.9, 10.3, 10.8),
            (10.8, 11.3, 10.7, 11.2),
        ])
        res = atom.check(klines, 2, {})
        assert res['is_valid'] is True
        assert res['value'] == 1.0  # 3 连阳命中，归一化封顶 1.0

    def test_normalized_strength_in_range(self):
        """归一化强度必须在 [0,1]（pattern_scanner 依赖）"""
        from structure_engine.morphology.atomic.shadow_ratio import ShadowRatio
        atom = ShadowRatio(shadow_type='upper', min_ratio=2.5)
        for v in [-1, 0, 0.5, 1, 2, 5]:
            n = atom.normalize(v)
            assert 0 <= n <= 1.0


class TestScanPatterns:
    def test_scan_returns_list(self):
        """scan_patterns 必须返回列表（空结果也允许）"""
        from structure_engine.scanner.pattern_scanner import scan_patterns
        import pandas as pd
        ohlc = pd.DataFrame(
            make_klines([(10.0, 10.4, 9.9, 10.3)] * 10),
            index=pd.date_range('2026-01-01', periods=10, freq='D'),
        )
        results = scan_patterns(ohlc, debug=False)
        assert isinstance(results, list)

    def test_scan_results_have_date_and_strength(self):
        """扫描结果每项须含 date/strength/category（回测融合依赖）"""
        from structure_engine.scanner.pattern_scanner import scan_patterns
        import pandas as pd
        rows = [(10.0 + i * 0.1, 10.0 + i * 0.1 + 0.3, 10.0 + i * 0.1 - 0.1, 10.0 + i * 0.1 + 0.2)
                for i in range(15)]
        ohlc = pd.DataFrame(
            make_klines(rows),
            index=pd.date_range('2026-01-01', periods=15, freq='D'),
        )
        results = scan_patterns(ohlc, debug=False)
        for r in results:
            assert 'date' in r
            assert 'strength' in r
            assert 'category' in r
