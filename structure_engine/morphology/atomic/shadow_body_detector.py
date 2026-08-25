"""
影线+实体组合原子特征（单根K线）
用于：射击之星 / 倒锤子线 / 上吊线
判定：
  shadow_type=upper → 上影线 >= 实体 * min_shadow_ratio
  shadow_type=lower → 下影线 >= 实体 * min_shadow_ratio
  实体比例 <= max_body_ratio（实体相对整根偏小）
  direction=bullish → 收盘 >= 开盘（实体位于下端）
  direction=bearish → 收盘 <= 开盘（实体位于上端）

设计说明：射击之星与倒锤子线几何条件相同（上影线长+实体小），
用阴阳方向区分——倒锤子线实体偏阳（下），射击之星实体偏阴（上）。
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class ShadowBodyDetector(AtomicFeature):
    def __init__(self, shadow_type: str = "upper", min_shadow_ratio: float = 2.0,
                 max_body_ratio: float = 0.5, direction: str = "bullish"):
        self.shadow_type = shadow_type
        self.min_shadow_ratio = min_shadow_ratio
        self.max_body_ratio = max_body_ratio
        self.direction = direction

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 0 or idx >= len(klines):
            return {"value": 0.0, "is_valid": False, "details": {"error": "idx out of range"}}

        k = klines[idx]
        body = abs(k['close'] - k['open'])
        high_low = k['high'] - k['low']
        if body <= 0 or high_low <= 0:
            return {"value": 0.0, "is_valid": False, "details": {"shadow_body": 0.0}}

        if self.shadow_type == "upper":
            shadow = k['high'] - max(k['open'], k['close'])
        else:
            shadow = min(k['open'], k['close']) - k['low']
        shadow = max(0.0, shadow)

        ratio = shadow / body            # 影线 / 实体
        body_ratio = body / high_low     # 实体 / 整根

        if self.direction == "bullish":
            direction_ok = k['close'] >= k['open']
        elif self.direction == "bearish":
            direction_ok = k['close'] <= k['open']
        else:
            direction_ok = True

        is_valid = direction_ok and ratio >= self.min_shadow_ratio and body_ratio <= self.max_body_ratio

        return {
            "value": ratio,
            "is_valid": is_valid,
            "details": {
                "shadow_type": self.shadow_type,
                "shadow_ratio": round(ratio, 3),
                "body_ratio": round(body_ratio, 3),
                "direction": self.direction
            }
        }

    def normalize(self, value: float) -> float:
        """影线/实体比值：以自身 min_shadow_ratio 为基准，达到其 2 倍即满格"""
        cap = self.min_shadow_ratio * 2
        return min(1.0, value / cap) if cap > 0 else min(1.0, max(0.0, value))
