"""
原子特征基类
所有原子函数必须实现 check() 方法，返回数值特征
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class AtomicFeature(ABC):
    @abstractmethod
    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        统一返回格式:
        {
            "value": float,      # 特征数值
            "is_valid": bool,    # 数据是否有效
            "details": dict      # 可选：额外调试信息
        }
        """
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def normalize(self, value: float) -> float:
        """
        将原始原子值归一化到 [0, 1]。
        默认实现直接截断（大多数原子天然 0~1）；
        值域可超过 1 的原子（影线类、连续K线等）需覆盖此方法。
        """
        return min(1.0, max(0.0, value))