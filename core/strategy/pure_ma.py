# -*- coding: utf-8 -*-
"""
纯双均线金叉策略（PureMACrossStrategy）
=================================================================
2026-09-02 老板："库里面有没有更简单的双均线金叉？我们的版本比较极端"
实验对照（关止损、2022-06~2026-08、84池）：
  - 纯金叉（上穿买/下穿卖）: +133.0% / Sharpe 0.98 / 回撤 -24.1%  ← 84池胜出
  - 裸 SimpleStrategy:      +56.7%  / Sharpe 0.58 / 回撤 -29.5%
  - 精选15: 纯金叉 +281% vs 裸Simple +456%（好票池复杂版仍胜出）
结论：普通票池（84）"纯金叉更干净"——无加速度拐点/无加仓节奏/无质量/无筑底/无位置，
     上穿 MA20 买、下穿 MA20 卖，是最朴素的双均线金叉。好票池（精选15）复杂逻辑有溢价。

实现要点：
  - score_stocks: MA5 上穿 MA20（前一日差≤0 且今日差>0）= 金叉 → 评分 1.0（买入信号）
                 其余 → 0.0（无新信号）。金叉后持仓由引擎保持，直到死叉。
  - get_exit_signal: MA5 下穿 MA20 = 死叉 → exit=True（卖出）
  - 纯区间切换：金叉区不重复买、死叉区不操作，等下次交叉。
  - 不继承 SimpleStrategy（无 prepare 特征矩阵/质量/位置/筑底/加速度——刻意保持极简），
    直接实现 BaseStrategy 接口；window/lookback 供引擎 warmup。
"""
import pandas as pd

from .base import BaseStrategy


class PureMACrossStrategy(BaseStrategy):
    """教科书双均线金叉：MA5 上穿 MA20 买，MA5 下穿 MA20 卖。无任何附加。"""

    def __init__(self, short: int = 5, long: int = 20, verbose: bool = False):
        self.short = short
        self.long = long
        self.verbose = verbose
        # 引擎 warmup 参考（与 Simple 一致：至少 long+1 根算均线）
        self.window = long + 1
        self.lookback = long + 1

    # ---------- 计算 ----------
    def _diff(self, series):
        """归一化价格序列的 MA5-MA20 差序列"""
        price = (1 + series).cumprod() * 100
        ma5 = price.rolling(self.short).mean()
        ma20 = price.rolling(self.long).mean()
        return ma5, ma20, (ma5 - ma20)

    def score_stocks(self, returns_df: pd.DataFrame, market_ret=None) -> pd.Series:
        """金叉（昨差≤0 且 今差>0）→ 1.0；否则 0.0。返回按分降序的 Series。"""
        out = {}
        for code in returns_df.columns:
            s = returns_df[code].dropna()
            if len(s) < self.long + 1:
                continue
            _, _, diff = self._diff(s)
            if len(diff) < 3:
                continue
            prev_d, curr_d = diff.iloc[-2], diff.iloc[-1]
            if pd.isna(prev_d) or pd.isna(curr_d):
                continue
            out[code] = 1.0 if (prev_d <= 0 < curr_d) else 0.0
        return pd.Series(out).sort_values(ascending=False)

    def get_exit_signal(self, returns_df: pd.DataFrame, market_ret=None) -> dict:
        """死叉（昨差≥0 且 今差<0）→ exit=True。返回 {code: {'exit': bool,...}}（pipeline 契约）。"""
        out = {}
        for code in returns_df.columns:
            s = returns_df[code].dropna()
            if len(s) < self.long + 1:
                continue
            _, _, diff = self._diff(s)
            if len(diff) < 3:
                continue
            prev_d, curr_d = diff.iloc[-2], diff.iloc[-1]
            if pd.isna(prev_d) or pd.isna(curr_d):
                out[code] = {'exit': False, 'pct_250d_high': None, 'bottom_divergence': False}
                continue
            exit_flag = (prev_d >= 0 > curr_d)  # MA5 下穿 MA20
            out[code] = {'exit': exit_flag, 'pct_250d_high': None, 'bottom_divergence': False}
        return out
