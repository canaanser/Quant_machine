"""
吞没检测原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class EngulfingDetector(AtomicFeature):
    def __init__(self, engulfing_type: str = "bullish"):
        self.engulfing_type = engulfing_type

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 1 or idx >= len(klines):
            return {"value": 0.0, "is_valid": False, "details": {"error": "idx out of range"}}

        curr = klines[idx]
        prev = klines[idx - 1]

        curr_open = curr['open']
        curr_close = curr['close']
        prev_open = prev['open']
        prev_close = prev['close']

        curr_body_low = min(curr_open, curr_close)
        curr_body_high = max(curr_open, curr_close)
        prev_body_low = min(prev_open, prev_close)
        prev_body_high = max(prev_open, prev_close)

        if self.engulfing_type == "bullish":
            is_bullish = curr_close > curr_open
            prev_is_bearish = prev_close < prev_open
            engulf = is_bullish and prev_is_bearish and curr_body_low < prev_body_low and curr_body_high > prev_body_high
            engulf_ratio = (curr_body_high - curr_body_low) / (prev_body_high - prev_body_low + 0.001)
        else:
            is_bearish = curr_close < curr_open
            prev_is_bullish = prev_close > prev_open
            engulf = is_bearish and prev_is_bullish and curr_body_low < prev_body_low and curr_body_high > prev_body_high
            engulf_ratio = (curr_body_high - curr_body_low) / (prev_body_high - prev_body_low + 0.001)

        value = engulf_ratio if engulf else 0.0
        return {
            "value": min(1.0, value),
            "is_valid": engulf,
            "details": {
                "engulfing_type": self.engulfing_type,
                "engulf_ratio": round(engulf_ratio, 3) if engulf else 0.0
            }
        }