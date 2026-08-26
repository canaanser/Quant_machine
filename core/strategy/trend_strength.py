# -*- coding: utf-8 -*-
"""
趋势强度驱动策略（双均线升级版，连续仓位系数）
（2026-08-26 小二陈：从 core/strategy.py 拆出，接口不变）
"""
import pandas as pd
from .base import BaseStrategy

class TrendStrengthStrategy(BaseStrategy):
    """
    趋势强度驱动策略（双均线升级版）
    输出连续仓位系数（0~1），而非离散买卖信号。
    作为可选策略，不替代原有 SimpleStrategy。

    核心逻辑：
        1. 趋势强度 = 均线偏离度 + MACD动量 + MACD加速度 加权合成
        2. 仓位系数 = 趋势强度映射到 0~1，低于阈值时清仓
        3. 死叉兜底：当 MA5 < MA20 且趋势强度 < 0.3 时强制返回 0.0
    """

    def __init__(
        self,
        short=5,
        long=20,
        macd_short=12,
        macd_long=26,
        macd_signal=9,
        position_weight=0.4,
        momentum_weight=0.4,
        acceleration_weight=0.2,
        trend_threshold=0.25,
        curve_power=1.5,
        verbose: bool = False
    ):
        self.short = short
        self.long = long
        self.macd_short = macd_short
        self.macd_long = macd_long
        self.macd_signal = macd_signal
        self.position_weight = position_weight
        self.momentum_weight = momentum_weight
        self.acceleration_weight = acceleration_weight
        self.trend_threshold = trend_threshold
        self.curve_power = curve_power
        self.window = long + 1
        self.lookback = long + 1
        self.verbose = verbose

    def score_stocks(self, returns_df: pd.DataFrame, market_ret: pd.Series) -> pd.Series:
        """
        主入口：返回每只股票的评分（0~1 连续值）。
        与 SimpleStrategy 接口一致，可无缝替换。
        """
        scores = {}
        for code in returns_df.columns:
            series = returns_df[code].dropna()
            if len(series) < self.long + self.macd_long + 5:
                continue

            # 从收益率重建价格序列
            price_series = (1 + series).cumprod() * 100

            # 计算 MA5 和 MA20
            ma5 = price_series.rolling(self.short).mean()
            ma20 = price_series.rolling(self.long).mean()

            # 计算 MACD
            exp1 = price_series.ewm(span=self.macd_short, adjust=False).mean()
            exp2 = price_series.ewm(span=self.macd_long, adjust=False).mean()
            macd_line = exp1 - exp2
            macd_signal_line = macd_line.ewm(span=self.macd_signal, adjust=False).mean()
            macd_hist = macd_line - macd_signal_line

            # 构建 DataFrame 供内部方法使用
            df = pd.DataFrame({
                'ma5': ma5,
                'ma20': ma20,
                'macd_hist': macd_hist,
                'macd_line': macd_line,
                'macd_signal': macd_signal_line,
                'price': price_series,
            })

            # 丢弃 NaN 行
            df = df.dropna()
            if len(df) < 5:
                continue

            # 死叉兜底：MA5 < MA20 且趋势强度低时强制清仓
            if df['ma5'].iloc[-1] < df['ma20'].iloc[-1]:
                trend = self._calc_trend_strength(df)
                if trend < 0.3:
                    scores[code] = 0.0
                    continue

            # 正常计算趋势强度和仓位系数
            trend_strength = self._calc_trend_strength(df)
            position_ratio = self._calc_position_ratio(trend_strength)

            # 最终评分 = 仓位系数（0~1 连续值）
            scores[code] = min(1.0, max(0.0, position_ratio))

        return pd.Series(scores).sort_values(ascending=False)

    def get_exit_signal(self, returns_df: pd.DataFrame, market_ret: pd.Series) -> pd.Series:
        """
        TrendStrengthStrategy的退出信号：
        当趋势强度低于阈值时清仓（连续仓位降为0）
        """
        scores = self.score_stocks(returns_df, market_ret)
        return scores < 0.01

    def _calc_trend_strength(self, df: pd.DataFrame) -> float:
        """
        计算趋势强度（0~1），由均线偏离度、MACD动量、MACD加速度加权合成
        """
        if len(df) < 5:
            return 0.0

        # 1) 均线偏离度（位置）
        ma5 = df['ma5'].iloc[-1]
        ma20 = df['ma20'].iloc[-1]
        if ma20 == 0 or pd.isna(ma20):
            deviation = 0
        else:
            deviation = (ma5 - ma20) / ma20
        position_score = 0.5 + min(0.5, deviation * 5)  # 偏离5%即满权重
        position_score = min(1.0, max(0.0, position_score))

        # 2) MACD柱状体方向（动量）
        macd_hist = df['macd_hist'].iloc[-1]
        hist_max = df['macd_hist'].max() if df['macd_hist'].max() > 0 else 0.001
        hist_min = df['macd_hist'].min() if df['macd_hist'].min() < 0 else -0.001

        if macd_hist > 0:
            momentum_score = min(1.0, macd_hist / max(hist_max, 0.001))
        else:
            momentum_score = max(0.0, 1.0 + macd_hist / max(abs(hist_min), 0.001))
        momentum_score = min(1.0, max(0.0, momentum_score))

        # 3) MACD柱体斜率（加速度）——最近5天的变化率
        if len(df) >= 5:
            macd_5d_change = df['macd_hist'].iloc[-1] - df['macd_hist'].iloc[-5]
            # 用 0.05 作为归一化基准，变化超过5%即满权重
            acceleration_score = min(1.0, max(0.0, macd_5d_change / 0.05))
        else:
            acceleration_score = 0.0

        # 加权合成
        trend_strength = (
            self.position_weight * position_score +
            self.momentum_weight * momentum_score +
            self.acceleration_weight * acceleration_score
        )
        return min(1.0, max(0.0, trend_strength))

    def _calc_position_ratio(self, trend_strength: float) -> float:
        """
        将趋势强度映射为仓位系数（0~1）
        低于阈值时清仓，高于阈值时按幂次曲线映射
        """
        if trend_strength < self.trend_threshold:
            return 0.0

        ratio = (trend_strength - self.trend_threshold) / (1 - self.trend_threshold)
        return min(1.0, ratio ** self.curve_power)