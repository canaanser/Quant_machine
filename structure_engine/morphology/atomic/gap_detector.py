"""
跳空检测原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class GapDetector(AtomicFeature):
    def __init__(self, gap_type: str = "up", min_gap_ratio: float = 0.01):
        self.gap_type = gap_type
        self.min_gap_ratio = min_gap_ratio

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 1 or idx >= len(klines):
            return {"value": 0.0, "is_valid": False, "details": {"error": "idx out of range"}}

        curr = klines[idx]
        prev = klines[idx - 1]
        prev_close = prev['close']

        if self.gap_type == "up":
            gap = curr['low'] - prev_close
            value = gap / prev_close if prev_close > 0 else 0.0
            details = {"gap_up": round(gap, 3), "gap_ratio": round(value, 4)}
        else:
            gap = prev_close - curr['high']
            value = gap / prev_close if prev_close > 0 else 0.0
            details = {"gap_down": round(gap, 3), "gap_ratio": round(value, 4)}

        is_valid = value > 0
        return {"value": max(0.0, value), "is_valid": is_valid, "details": details}