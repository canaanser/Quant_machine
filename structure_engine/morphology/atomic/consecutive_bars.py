"""
连续同色K线原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class ConsecutiveBars(AtomicFeature):
    def __init__(self, direction: str = "up", count: int = 3):
        self.direction = direction
        self.count = count

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < self.count - 1 or idx >= len(klines):
            return {"value": 0.0, "is_valid": False, "details": {"error": "idx out of range"}}

        consecutive = 0
        for i in range(idx - self.count + 1, idx + 1):
            k = klines[i]
            if self.direction == "up":
                if k['close'] > k['open']:
                    consecutive += 1
                else:
                    break
            else:
                if k['close'] < k['open']:
                    consecutive += 1
                else:
                    break

        value = consecutive / self.count
        is_valid = consecutive >= self.count
        return {
            "value": value,
            "is_valid": is_valid,
            "details": {
                "direction": self.direction,
                "consecutive_count": consecutive,
                "target_count": self.count
            }
        }

    def normalize(self, value: float) -> float:
        """连续数/目标数（匹配时 >=1，可到 1.67）：达到目标数即满格"""
        return min(1.0, max(0.0, value))