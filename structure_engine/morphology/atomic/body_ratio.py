"""
实体比例原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class BodyRatio(AtomicFeature):
    def __init__(self, min_ratio: float = 0.25, max_ratio: float = 0.65):
        self.min_ratio = min_ratio
        self.max_ratio = max_ratio

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 0 or idx >= len(klines):
            return {"value": 0.0, "is_valid": False, "details": {"error": "idx out of range"}}

        k = klines[idx]
        body = abs(k['close'] - k['open'])
        high_low = k['high'] - k['low']
        if high_low == 0:
            return {"value": 0.0, "is_valid": False, "details": {"body_ratio": 0.0}}

        ratio = body / high_low
        return {"value": ratio, "is_valid": True, "details": {"body_ratio": round(ratio, 3)}}