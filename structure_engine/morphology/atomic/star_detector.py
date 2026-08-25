"""
早晨之星 / 黄昏之星原子特征（三根组合）
判定（以 idx 为第三根K线）：
  morning（早晨之星）：b1 大阴线 + b2 小实体 + b3 大阳线
  evening（黄昏之星）：b1 大阳线 + b2 小实体 + b3 大阴线
value = 1.0（成立）/ 0.0，is_valid = 形态成立
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class StarDetector(AtomicFeature):
    def __init__(self, star_type: str = "morning", body_threshold: float = 0.5, small_threshold: float = 0.3):
        self.star_type = star_type
        self.body_threshold = body_threshold
        self.small_threshold = small_threshold

    @staticmethod
    def _body_ratio(k) -> float:
        high_low = k['high'] - k['low']
        if high_low <= 0:
            return 0.0
        return abs(k['close'] - k['open']) / high_low

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 2 or idx >= len(klines):
            return {"value": 0.0, "is_valid": False, "details": {"error": "idx out of range"}}

        b1, b2, b3 = klines[idx - 2], klines[idx - 1], klines[idx]

        r1 = self._body_ratio(b1)
        r2 = self._body_ratio(b2)
        r3 = self._body_ratio(b3)

        b1_bull = b1['close'] > b1['open']
        b1_bear = b1['close'] < b1['open']
        b3_bull = b3['close'] > b3['open']
        b3_bear = b3['close'] < b3['open']

        if self.star_type == "morning":
            # 大阴线 → 小实体 → 大阳线
            ok = (b1_bear and r1 >= self.body_threshold and
                  r2 <= self.small_threshold and
                  b3_bull and r3 >= self.body_threshold)
        else:
            # 大阳线 → 小实体 → 大阴线
            ok = (b1_bull and r1 >= self.body_threshold and
                  r2 <= self.small_threshold and
                  b3_bear and r3 >= self.body_threshold)

        return {
            "value": 1.0 if ok else 0.0,
            "is_valid": ok,
            "details": {
                "star_type": self.star_type,
                "body_ratios": [round(r1, 3), round(r2, 3), round(r3, 3)]
            }
        }
