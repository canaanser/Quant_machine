"""
形态生成框架测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
from structure_engine.morphology import REGISTRY
from structure_engine.morphology.atomic import (
    BodyRatio,
    ShadowRatio,
    GapDetector,
    EngulfingDetector,
    InsideDetector,
    ConsecutiveBars,
    VolumeSpike,
)


class TestMorphology(unittest.TestCase):

    def test_registry(self):
        """测试注册表是否正常加载"""
        patterns = REGISTRY.list_all()
        self.assertGreater(len(patterns), 5)
        print(f"注册表加载: {len(patterns)} 个形态")

    def test_body_ratio(self):
        """测试实体比例原子特征"""
        atom = BodyRatio(min_ratio=0.25, max_ratio=0.65)
        klines = [{"open": 10, "close": 12, "high": 13, "low": 9, "volume": 100}]
        result = atom.check(klines, 0, {})
        self.assertTrue(result['is_valid'])                    # 用 is_valid 替代 matched
        self.assertAlmostEqual(result['details']['body_ratio'], 0.5, delta=0.01)

    def test_shadow_ratio(self):
        """测试影线比例原子特征"""
        atom = ShadowRatio(shadow_type="upper", min_ratio=2.5)
        klines = [{"open": 10, "close": 11, "high": 15, "low": 9.5, "volume": 100}]
        result = atom.check(klines, 0, {})
        self.assertTrue(result['is_valid'])
        self.assertGreater(result['value'], 2.4)


if __name__ == "__main__":
    unittest.main()