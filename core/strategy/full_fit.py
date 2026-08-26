# -*- coding: utf-8 -*-
"""
完全拟合策略（全满分）
（2026-08-26 小二陈：从 core/strategy.py 拆出，接口不变）
"""
import pandas as pd
from .base import BaseStrategy

class FullFitStrategy(BaseStrategy):
    def __init__(self):
        self.window = 1
        self.lookback = 1

    def score_stocks(self, returns_df, market_ret):
        scores = {code: 1.0 for code in returns_df.columns}
        return pd.Series(scores).sort_values(ascending=False)

    def get_exit_signal(self, returns_df: pd.DataFrame, market_ret: pd.Series) -> pd.Series:
        return pd.Series(False, index=returns_df.columns)


