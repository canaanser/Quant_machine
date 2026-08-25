"""
索引引擎测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
import tempfile
import json
from structure_engine.index_engine import IndexStore, query_similar
from structure_engine.schemas import StateTable


class TestIndexEngine(unittest.TestCase):

    def test_index_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = IndexStore(db_path)

            record = {
                "symbol": "000063",
                "start_date": "20260608",
                "end_date": "20260710",
                "segment_type": "上升段",
                "features": {"kline_shape": [0.5, 0.6, 0.7]},
                "tags": ["放量上涨"],
                "best_buy": {"date": "20260608", "price": 36.37},
                "best_sell": {"date": "20260710", "price": 40.05},
                "ma_buy": {},
                "ma_sell": {},
                "data_pointer": {},
                "forward_stats": {"d20_return": 0.087},
                "amplitude": 0.10,
                "duration": 30,
            }

            index_id = store.insert(record)
            self.assertIsNotNone(index_id)

            results = store.search({"amplitude": 0.10, "duration": 30})
            self.assertGreaterEqual(len(results), 1)

    def test_state_table_format(self):
        mock_state = StateTable(
            date="2026-08-12",
            symbol="000063",
            pattern_ids=["2_bullish_0_engulfing"],
            strength=0.72,
            category="bullish"
        )
        self.assertTrue(hasattr(mock_state, "pattern_ids"))
        self.assertTrue(hasattr(mock_state, "strength"))
        self.assertEqual(mock_state.symbol, "000063")
        d = mock_state.to_dict()
        self.assertIn("pattern_ids", d)
        self.assertIn("strength", d)
        print("StateTable 格式验证通过")


if __name__ == "__main__":
    unittest.main()
