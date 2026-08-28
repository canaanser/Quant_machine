"""策略层：所有策略在此导出（2026-08-26 拆分自 core/strategy.py，接口不变）
2026-08-28 小二陈：删除 TrendStrategy（与 Alpha 退化分支重复）与 FullFitStrategy（占位对照）"""
from .base import BaseStrategy
from .alpha import AlphaScoreStrategy
from .simple import SimpleStrategy
from .trend_strength import TrendStrengthStrategy

__all__ = [
    'BaseStrategy', 'AlphaScoreStrategy',
    'SimpleStrategy', 'TrendStrengthStrategy',
]
