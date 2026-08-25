"""
影线比例原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class ShadowRatio(AtomicFeature):
    def __init__(self, shadow_type: str = "upper", min_ratio: float = 2.5):
        self.shadow_type = shadow_type
        self.min_ratio = min_ratio

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 0 or idx >= len(klines):
            return {"value": 0.0, "is_valid": False, "details": {"error": "idx out of range"}}

        k = klines[idx]
        body = abs(k['close'] - k['open'])
        if body == 0:
            return {"value": 0.0, "is_valid": False, "details": {"shadow_ratio": 0.0}}

        if self.shadow_type == "upper":
            shadow = k['high'] - max(k['open'], k['close'])
        else:
            shadow = min(k['open'], k['close']) - k['low']

        shadow = max(0.0, shadow)
        ratio = shadow / body
        return {"value": ratio, "is_valid": True, "details": {f"{self.shadow_type}_shadow_ratio": round(ratio, 3)}}