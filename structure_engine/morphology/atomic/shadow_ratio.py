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

    def normalize(self, value: float) -> float:
        """影线/实体比值（可到 20+）：以形态自身阈值为基准，达到 min_ratio 的 2 倍即满格"""
        cap = self.min_ratio * 2
        value = max(0.0, value)  # 防御：负值截断到 0（check() 正常返回恒 >=0）
        return min(1.0, value / cap) if cap > 0 else min(1.0, max(0.0, value))