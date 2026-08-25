"""
方向性长实体原子特征
用于：长阳线（bullish）/ 长阴线（bearish）
判定：实体比例 >= min_ratio，且方向匹配（收盘 > 开盘 = 阳线 / 收盘 < 开盘 = 阴线）
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class DirectionalBody(AtomicFeature):
    def __init__(self, direction: str = "bullish", min_ratio: float = 0.65):
        self.direction = direction
        self.min_ratio = min_ratio

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 0 or idx >= len(klines):
            return {"value": 0.0, "is_valid": False, "details": {"error": "idx out of range"}}

        k = klines[idx]
        high_low = k['high'] - k['low']
        if high_low <= 0:
            return {"value": 0.0, "is_valid": False, "details": {"directional_body": 0.0}}

        body = abs(k['close'] - k['open'])
        ratio = body / high_low

        if self.direction == "bullish":
            direction_ok = k['close'] > k['open']
        else:
            direction_ok = k['close'] < k['open']

        is_valid = direction_ok and ratio >= self.min_ratio
        return {
            "value": ratio,
            "is_valid": is_valid,
            "details": {
                "direction": self.direction,
                "body_ratio": round(ratio, 3),
                "min_ratio": self.min_ratio
            }
        }
