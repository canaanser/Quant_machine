"""
上升三法 / 下降三法原子特征（五根组合）
判定（以 idx 为第五根K线）：
  rising（上升三法）：b1 大阳线 → b2~b4 三根小K线（在 b1 实体范围内回调）→ b5 大阳线收盘突破 b1 收盘
  falling（下降三法）：b1 大阴线 → b2~b4 三根小K线（在 b1 实体范围内反弹）→ b5 大阴线收盘跌破 b1 收盘
value = 1.0（成立）/ 0.0，is_valid = 形态成立
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class ThreeMethodsDetector(AtomicFeature):
    def __init__(self, pattern_type: str = "rising", body_threshold: float = 0.5, small_threshold: float = 0.4):
        self.pattern_type = pattern_type
        self.body_threshold = body_threshold
        self.small_threshold = small_threshold

    @staticmethod
    def _body_ratio(k) -> float:
        high_low = k['high'] - k['low']
        if high_low <= 0:
            return 0.0
        return abs(k['close'] - k['open']) / high_low

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 4 or idx >= len(klines):
            return {"value": 0.0, "is_valid": False, "details": {"error": "idx out of range"}}

        b1 = klines[idx - 4]
        middle = klines[idx - 3:idx]  # b2~b4
        b5 = klines[idx]

        r1 = self._body_ratio(b1)
        r5 = self._body_ratio(b5)
        # 中间三根须在 b1 实体范围内整理（标准定义：收盘价不破 b1 实体）
        body_low_1 = min(b1['open'], b1['close'])
        body_high_1 = max(b1['open'], b1['close'])

        # 中间三根必须是小实体且收盘价在 b1 实体范围内
        middle_ok = True
        for m in middle:
            if self._body_ratio(m) > self.small_threshold:
                middle_ok = False
                break
            if m['close'] > body_high_1 or m['close'] < body_low_1:
                middle_ok = False
                break

        if not middle_ok:
            return {"value": 0.0, "is_valid": False, "details": {"pattern_type": self.pattern_type, "reason": "middle_bars"}}

        # 第5根：同向实体（阈值略宽松）且收盘突破 b1 收盘
        b5_threshold = max(self.body_threshold * 0.8, 0.4)
        if self.pattern_type == "rising":
            ok = (b1['close'] > b1['open'] and r1 >= self.body_threshold and
                  b5['close'] > b5['open'] and r5 >= b5_threshold and
                  b5['close'] > b1['close'])
        else:
            ok = (b1['close'] < b1['open'] and r1 >= self.body_threshold and
                  b5['close'] < b5['open'] and r5 >= b5_threshold and
                  b5['close'] < b1['close'])

        return {
            "value": 1.0 if ok else 0.0,
            "is_valid": ok,
            "details": {
                "pattern_type": self.pattern_type,
                "b1_ratio": round(r1, 3),
                "b5_ratio": round(r5, 3)
            }
        }
