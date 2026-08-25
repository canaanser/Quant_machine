"""
量能突增原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class VolumeSpike(AtomicFeature):
    def __init__(self, lookback: int = 5, multiplier: float = 1.8):
        self.lookback = lookback
        self.multiplier = multiplier

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < self.lookback or idx >= len(klines):
            return {"value": 0.0, "is_valid": False, "details": {"error": "idx out of range"}}

        curr_vol = klines[idx]['volume']
        avg_vol = sum([klines[i]['volume'] for i in range(idx - self.lookback, idx)]) / self.lookback

        if avg_vol == 0:
            return {"value": 0.0, "is_valid": False, "details": {"avg_volume": 0}}

        ratio = curr_vol / avg_vol
        value = min(1.0, (ratio - 1) / 4)
        is_valid = ratio >= self.multiplier
        return {
            "value": max(0.0, value),
            "is_valid": is_valid,
            "details": {
                "current_volume": curr_vol,
                "avg_volume": round(avg_vol),
                "ratio": round(ratio, 2)
            }
        }