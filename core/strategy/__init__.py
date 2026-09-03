"""策略层：所有策略在此导出（2026-08-26 拆分自 core/strategy.py，接口不变）
2026-08-28 小二陈：删除 TrendStrategy（与 Alpha 退化分支重复）、FullFitStrategy（占位对照）、
TrendStrengthStrategy（趋势强度，组合层面 84 只 10 年：收益 1/4、回撤 -80%、Sharpe 0.38，全面落败于双均线金叉）
2026-08-28 小二陈：新增 DualLegStrategy（双腿融合，从 SimpleStrategy 衍生：死叉区抄底腿 + 金叉区趋势腿，
解决 Simple 踏空趋势行情问题；同一评分体系双腿并存，自动接力）
2026-09-02 小二陈：新增 PureMACrossStrategy（纯双均线金叉，教科书版，老板"我们的版本太极端"——
84池实证 纯金叉+133%/Sharpe0.98/-24% 完胜裸Simple +56.7%/0.58/-29.5%，见 pure_ma.py 头注释）"""
from .base import BaseStrategy
from .alpha import AlphaScoreStrategy
from .simple import SimpleStrategy
from .dual_leg import DualLegStrategy
from .pure_ma import PureMACrossStrategy

__all__ = [
    'BaseStrategy', 'AlphaScoreStrategy', 'SimpleStrategy', 'DualLegStrategy',
    'PureMACrossStrategy',
]
