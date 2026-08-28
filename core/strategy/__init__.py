"""策略层：所有策略在此导出（2026-08-26 拆分自 core/strategy.py，接口不变）
2026-08-28 小二陈：删除 TrendStrategy（与 Alpha 退化分支重复）、FullFitStrategy（占位对照）、
TrendStrengthStrategy（趋势强度，组合层面 84 只 10 年：收益 1/4、回撤 -80%、Sharpe 0.38，全面落败于双均线金叉）"""
from .base import BaseStrategy
from .alpha import AlphaScoreStrategy
from .simple import SimpleStrategy

__all__ = [
    'BaseStrategy', 'AlphaScoreStrategy', 'SimpleStrategy',
]
