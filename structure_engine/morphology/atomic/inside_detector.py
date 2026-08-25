"""
内包检测原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class InsideDetector(AtomicFeature):
    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 1 or idx >= len(klines):
            return {"value": 0.0, "is_valid": False, "details": {"error": "idx out of range"}}

        curr = klines[idx]
        prev = klines[idx - 1]

        curr_body_low = min(curr['open'], curr['close'])
        curr_body_high = max(curr['open'], curr['close'])
        prev_body_low = min(prev['open'], prev['close'])
        prev_body_high = max(prev['open'], prev['close'])

        inside = curr_body_low > prev_body_low and curr_body_high < prev_body_high
        curr_range = curr_body_high - curr_body_low
        prev_range = prev_body_high - prev_body_low
        ratio = curr_range / (prev_range + 0.001)

        value = min(1.0, (1 - ratio) * 2) if inside else 0.0
        return {"value": value, "is_valid": inside, "details": {"inside": inside, "range_ratio": round(ratio, 3)}}