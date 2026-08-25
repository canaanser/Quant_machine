"""
刺透/乌云盖顶原子特征（双根组合）
判定：
  dark_cloud（乌云盖顶）：b1 阳线，b2 高开低走阴线，收盘刺入 b1 实体超过 50%
  piercing（刺透线）：    b1 阴线，b2 低开高走阳线，收盘刺入 b1 实体超过 50%
value = 刺入深度（0~1），is_valid = 形态成立
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class PiercingDetector(AtomicFeature):
    def __init__(self, pattern_type: str = "dark_cloud", depth: float = 0.5):
        self.pattern_type = pattern_type
        self.depth = depth

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 1 or idx >= len(klines):
            return {"value": 0.0, "is_valid": False, "details": {"error": "idx out of range"}}

        prev = klines[idx - 1]
        curr = klines[idx]

        prev_open, prev_close = prev['open'], prev['close']
        curr_open, curr_close = curr['open'], curr['close']

        prev_body = abs(prev_close - prev_open)
        if prev_body <= 0:
            return {"value": 0.0, "is_valid": False, "details": {"piercing": 0.0}}

        if self.pattern_type == "dark_cloud":
            # b1 阳线，b2 阴线且高开，收盘从 b1 顶部向下刺入实体
            prev_bull = prev_close > prev_open
            curr_bear = curr_close < curr_open
            gap_up = curr_open > prev_close
            if prev_bull and curr_bear and gap_up:
                penetration = (prev_close - curr_close) / prev_body
                is_valid = penetration >= self.depth
                return {
                    "value": penetration,
                    "is_valid": is_valid,
                    "details": {"pattern_type": "dark_cloud", "penetration": round(penetration, 3), "depth": self.depth}
                }
        else:  # piercing
            # b1 阴线，b2 阳线且低开，收盘从 b1 底部向上刺入实体
            prev_bear = prev_close < prev_open
            curr_bull = curr_close > curr_open
            gap_down = curr_open < prev_close
            if prev_bear and curr_bull and gap_down:
                penetration = (curr_close - prev_close) / prev_body
                is_valid = penetration >= self.depth
                return {
                    "value": penetration,
                    "is_valid": is_valid,
                    "details": {"pattern_type": "piercing", "penetration": round(penetration, 3), "depth": self.depth}
                }

        return {"value": 0.0, "is_valid": False, "details": {"pattern_type": self.pattern_type, "penetration": 0.0}}
