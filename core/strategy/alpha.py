# -*- coding: utf-8 -*-
"""
Alpha 剥离策略（滚动OLS残差动量）
（2026-08-26 小二陈：从 core/strategy.py 拆出，接口不变）
"""
from core.logger import get_logger

logger = get_logger(__name__)

import pandas as pd
from statsmodels.regression.rolling import RollingOLS
import statsmodels.api as sm
from .base import BaseStrategy

class AlphaScoreStrategy(BaseStrategy):
    """
    极简Alpha剥离器（伪装成选股评价模块）
    输入：历史收益率宽表 + 市场基准收益率
    输出：每只股票今日的 Alpha 得分 (信息比率)
    """
    def __init__(self, window=60, lookback=20):
        self.window = window
        self.lookback = lookback

    def score_stocks(self, returns_df, market_ret):
        """
        returns_df: 各股票收益率 (行=日期, 列=股票代码)
        market_ret: 市场基准收益率 (Series)
        返回: Series (索引=股票代码, 值=Alpha得分)
        """
        stock_codes = returns_df.columns
        scores = {}
        
        # ----- 特殊情况：只有1只股票时，改用趋势跟踪策略 -----
        if len(stock_codes) <= 2:
            logger.debug(f"📊 股票池仅有 {len(stock_codes)} 只股票，使用趋势跟踪策略")
            for code in stock_codes:
                y = returns_df[code].dropna()
                if len(y) < self.window + self.lookback:
                    continue
                trend_score = y.iloc[-self.lookback:].mean()
                std_score = y.iloc[-self.lookback:].std() + 1e-6
                scores[code] = trend_score / std_score
            return pd.Series(scores).sort_values(ascending=False)
        
        # ----- 正常情况：多只股票使用滚动OLS回归 -----
        # 构建外生变量 (市场 + 常数项)
        exog = pd.DataFrame({'market': market_ret})
        exog = sm.add_constant(exog)  # 截距项对应Alpha
        
        for code in stock_codes:
            y = returns_df[code].dropna()
            common_idx = y.index.intersection(exog.index)
            if len(common_idx) < self.window + self.lookback:
                continue
                
            X_aligned = exog.loc[common_idx]
            y_aligned = y.loc[common_idx]
            
            try:
                model = RollingOLS(y_aligned, X_aligned, window=self.window)
                results = model.fit()
                
                # ---------- 修复：兼容不同版本的残差提取 ----------
                # 尝试获取残差
                if hasattr(results, 'resid'):
                    resid_series = results.resid
                elif hasattr(results, 'residuals'):
                    resid_series = results.residuals
                else:
                    # 手动计算残差：y - X @ params
                    params = results.params  # DataFrame, index=日期, columns=变量
                    if hasattr(results, 'fittedvalues'):
                        resid_series = y_aligned - results.fittedvalues
                    else:
                        # 兜底：遍历计算
                        resid_list = []
                        for i in range(self.window, len(y_aligned)):
                            y_i = y_aligned.iloc[i]
                            X_i = X_aligned.iloc[i]
                            beta = params.iloc[i - self.window]  # 对应窗口的参数
                            pred = (X_i * beta).sum()
                            resid_list.append(y_i - pred)
                        resid_series = pd.Series(resid_list, index=y_aligned.index[self.window:])
                
                # 确保残差是 Series
                if not isinstance(resid_series, pd.Series):
                    resid_series = pd.Series(resid_series, index=y_aligned.index[-len(resid_series):])
                
                if len(resid_series) >= self.lookback:
                    recent = resid_series.iloc[-self.lookback:]
                    scores[code] = recent.mean() / (recent.std() + 1e-6)
            except Exception as e:
                # 只打印一次，避免刷屏
                if not hasattr(self, '_error_printed'):
                    self._error_printed = set()
                if code not in self._error_printed:
                    logger.debug(f"⚠️ {code} 回归失败: {e}")
                    self._error_printed.add(code)
                continue
        
        return pd.Series(scores).sort_values(ascending=False)

    def get_exit_signal(self, returns_df: pd.DataFrame, market_ret: pd.Series) -> pd.Series:
        """
        Alpha策略的退出信号：评分低于0.01时清仓
        """
        scores = self.score_stocks(returns_df, market_ret)
        return scores < 0.01


