"""
扫描器测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
import pandas as pd
from structure_engine.scanner import detect_waves, scan_patterns


class TestScanner(unittest.TestCase):

    def test_wave_detector(self):
        df = pd.DataFrame({
            '最高价': [10, 11, 12, 11, 10, 9, 8, 7, 8, 9, 10],
            '最低价': [9, 10, 11, 10, 9, 8, 7, 6, 7, 8, 9],
        })
        waves = detect_waves(df, window_days=20, peak_valley_lookback=2)
        self.assertTrue(any(w['type'] == 'valley' for w in waves))
        self.assertTrue(any(w['type'] == 'peak' for w in waves))

    def test_pattern_scanner(self):
        df = pd.DataFrame({
            'open': [10, 10, 10],
            'high': [11, 11, 11],
            'low': [9, 9, 9],
            'close': [10, 10, 10],
            'volume': [100, 100, 100],
        })
        results = scan_patterns(df)
        print(f"形态扫描: {len(results)} 个匹配")


if __name__ == "__main__":
    unittest.main()