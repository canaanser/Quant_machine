# -*- coding: utf-8 -*-
"""
趋势跟踪策略（简单动量）
（2026-08-26 小二陈：从 core/strategy.py 拆出，接口不变）
"""
import pandas as pd
from .base import BaseStrategy

class TrendStrategy(BaseStrategy):
    """
    趋势跟踪策略：基于价格突破布林带或简单动量。
    这里简化为：过去 N 日收益率 > 0 则看多，否则看空。
    """
    def __init__(self, period=20):
        self.period = period
        self.window = period + 1
        self.lookback = period + 1

    def score_stocks(self, returns_df, market_ret):
        import pandas as pd
        scores = {}
        for code in returns_df.columns:
            series = returns_df[code].dropna()
            if len(series) < self.period:
                continue
            # 计算累计收益率（简单动量）
            total_return = series.iloc[-self.period:].sum()
            scores[code] = total_return  # 正数看多，负数看空
        return pd.Series(scores).sort_values(ascending=False)

    def get_exit_signal(self, returns_df: pd.DataFrame, market_ret: pd.Series) -> pd.Series:
        scores = self.score_stocks(returns_df, market_ret)
        return scores < 0


