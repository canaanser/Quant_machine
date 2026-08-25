"""
锤子线原子特征（正式版）
判定（看涨锤子线）：
  1. 下影线 >= 实体 * min_ratio（默认 2 倍）
  2. 实体相对整根K线偏小（body_ratio <= max_body_ratio，默认 0.5）
  3. 收盘 >= 开盘（阳线或平盘）
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class HammerDetector(AtomicFeature):
    def __init__(self, min_ratio: float = 2.0, max_body_ratio: float = 0.5):
        self.min_ratio = min_ratio
        self.max_body_ratio = max_body_ratio

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 0 or idx >= len(klines):
            return {"value": 0.0, "is_valid": False, "details": {"error": "idx out of range"}}

        k = klines[idx]
        body = abs(k['close'] - k['open'])
        high_low = k['high'] - k['low']
        if body <= 0 or high_low <= 0:
            return {"value": 0.0, "is_valid": False, "details": {"hammer": 0.0}}

        lower_shadow = min(k['open'], k['close']) - k['low']
        ratio = lower_shadow / body          # 下影线 / 实体
        body_ratio = body / high_low         # 实体 / 整根

        is_bullish_or_flat = k['close'] >= k['open']
        is_valid = is_bullish_or_flat and ratio >= self.min_ratio and body_ratio <= self.max_body_ratio

        return {
            "value": ratio,
            "is_valid": is_valid,
            "details": {
                "lower_shadow_ratio": round(ratio, 3),
                "body_ratio": round(body_ratio, 3),
                "min_ratio": self.min_ratio,
                "max_body_ratio": self.max_body_ratio
            }
        }

    def normalize(self, value: float) -> float:
        """下影线/实体比值：以自身 min_ratio 为基准，达到其 2 倍即满格"""
        cap = self.min_ratio * 2
        return min(1.0, value / cap) if cap > 0 else min(1.0, max(0.0, value))
