# -*- coding: utf-8 -*-
"""
策略基类：统一评分/退出接口 + 形态融合
（2026-08-26 小二陈：从 core/strategy.py 拆出，接口不变）
"""
from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    """策略基类：定义统一的评分接口和退出信号接口"""

    @abstractmethod
    def score_stocks(self, returns_df: pd.DataFrame, market_ret: pd.Series) -> pd.Series:
        """
        生成买入评分（0~1 连续值，或 -1 表示强制清仓）
        每个策略自己定义评分语义
        """
        pass

    @abstractmethod
    def get_exit_signal(self, returns_df: pd.DataFrame, market_ret: pd.Series) -> pd.Series:
        """
        返回退出信号：True 表示该标的需要清仓
        每个策略自己定义退出条件
        """
        pass

    def fuse_with_patterns(self, traditional_score: float, pattern_strength: float, w: float = 0.3) -> float:
        """
        形态融合（基类默认实现，2026-08-26 小二陈）：
        传统评分与形态强度的加权融合，输出归一到 [0,1]。
        所有策略继承此接口，回测管线可统一调用（TrendStrengthStrategy 等无需各自实现）。
        - traditional_score < 0（强清仓信号）时保持原值，形态不干预
        - pattern_strength 截断到 [0,1]（已标准化）
        """
        if traditional_score < 0:
            return traditional_score
        pattern_clipped = min(1.0, max(0.0, pattern_strength))
        final = (1 - w) * traditional_score + w * pattern_clipped
        return min(1.0, max(0.0, final))


