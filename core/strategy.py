# core/strategy.py
# Alpha剥离策略模块（滚动OLS残差动量）
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from config.risk_config import EARLY_SCORE_THRESHOLD, EARLY_SCORE_MAGNITUDE, EARLY_SCORE_NEUTRAL
from statsmodels.regression.rolling import RollingOLS
import statsmodels.api as sm


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
            print(f"📊 股票池仅有 {len(stock_codes)} 只股票，使用趋势跟踪策略")
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
                    print(f"⚠️ {code} 回归失败: {e}")
                    self._error_printed.add(code)
                continue
        
        return pd.Series(scores).sort_values(ascending=False)

    def get_exit_signal(self, returns_df: pd.DataFrame, market_ret: pd.Series) -> pd.Series:
        """
        Alpha策略的退出信号：评分低于0.01时清仓
        """
        scores = self.score_stocks(returns_df, market_ret)
        return scores < 0.01


class FullFitStrategy(BaseStrategy):
    def __init__(self):
        self.window = 1
        self.lookback = 1

    def score_stocks(self, returns_df, market_ret):
        scores = {code: 1.0 for code in returns_df.columns}
        return pd.Series(scores).sort_values(ascending=False)

    def get_exit_signal(self, returns_df: pd.DataFrame, market_ret: pd.Series) -> pd.Series:
        return pd.Series(False, index=returns_df.columns)


class SimpleStrategy(BaseStrategy):
    """
    双均线金叉策略（立即交叉响应）：
    - 金叉/死叉发生当天立即切换区间
    - 仓位分配：第1次10%（评分放大1倍），第2次80%（评分放大2倍），第3次10%（评分放大2倍）
    """
    def __init__(self, short=5, long=20, verbose: bool = False):
        self.short = short
        self.long = long
        self.window = long + 1
        self.lookback = long + 1
        self._buy_count = {}
        self.verbose = verbose

    def _get_position_weight(self, buy_count):
        weights = {0: 0.0, 1: 0.10, 2: 0.80, 3: 0.10}
        return weights.get(buy_count, 0.0)

    def fuse_with_patterns(self, traditional_score: float, pattern_strength: float, w: float = 0.3) -> float:
        if traditional_score < 0:
            return traditional_score
        pattern_clipped = min(1.0, max(0.0, pattern_strength))
        final = (1 - w) * traditional_score + w * pattern_clipped
        return min(1.0, max(0.0, final))

    def score_stocks(self, returns_df, market_ret):
        import pandas as pd
        import math
        scores = {}
        for code in returns_df.columns:
            series = returns_df[code].dropna()
            if len(series) < self.long + 1:
                continue
            
            if code not in self._buy_count:
                self._buy_count[code] = 0
            
            price_series = (1 + series).cumprod() * 100
            ma5 = price_series.rolling(self.short).mean()
            ma20 = price_series.rolling(self.long).mean()
            
            curr_ma5 = ma5.iloc[-1]
            curr_ma20 = ma20.iloc[-1]
            prev_ma5 = ma5.iloc[-2]
            prev_ma20 = ma20.iloc[-2]
            
            prev_diff = prev_ma5 - prev_ma20
            curr_diff = curr_ma5 - curr_ma20
            
            if prev_diff <= 0 and curr_diff > 0:
                is_golden_zone = True
                is_death_zone = False
                self._buy_count[code] = 0
                if self.verbose:
                    print(f"🔔 {code} 金叉发生，重置买入计数")
            elif prev_diff >= 0 and curr_diff < 0:
                is_golden_zone = False
                is_death_zone = True
                self._buy_count[code] = 0
                if self.verbose:
                    print(f"🔔 {code} 死叉发生，重置买入计数")
            else:
                is_golden_zone = curr_ma5 > curr_ma20
                is_death_zone = curr_ma5 < curr_ma20
            
            slope_t = ma5.iloc[-1] - ma5.iloc[-2]
            slope_t1 = ma5.iloc[-2] - ma5.iloc[-3]
            slope_t2 = ma5.iloc[-3] - ma5.iloc[-4]
            accel_t = slope_t - slope_t1
            accel_t1 = slope_t1 - slope_t2
            
            if is_golden_zone:
                if accel_t1 > 0 and accel_t < 0:
                    scores[code] = -1.0
                    self._buy_count[code] = 0
                else:
                    scores[code] = 0
                    
            elif is_death_zone:
                if accel_t1 < 0 and accel_t > 0:
                    if self._buy_count[code] < 3:
                        self._buy_count[code] += 1
                    weight = self._get_position_weight(self._buy_count[code])
                    base_score = min(0.8, max(0.1, abs(accel_t) * 10))
                    
                    buy_count = self._buy_count[code]
                    if buy_count == 1:
                        final_score = base_score * weight * 1.0
                    elif buy_count == 2:
                        final_score = base_score * weight * 2.0
                    elif buy_count == 3:
                        final_score = base_score * weight * 2.0
                    else:
                        final_score = 0.0
                    
                    final_score = min(0.9, final_score)
                    
                    if final_score > 0.001:
                        if self.verbose:
                            print(f"   📍 买入: 第{buy_count}次, 权重={weight:.0%}, 评分={final_score:.3f}")
                        scores[code] = final_score
                    else:
                        scores[code] = 0
                else:
                    scores[code] = 0
            else:
                scores[code] = 0
                
        return pd.Series(scores).sort_values(ascending=False)

    def get_exit_signal(self, returns_df: pd.DataFrame, market_ret: pd.Series) -> pd.Series:
        """
        SimpleStrategy的退出信号：
        - 评分 < -0.05 时清仓（沿用原有逻辑）
        """
        scores = self.score_stocks(returns_df, market_ret)
        return scores < -0.05

    # ==================== 早盘动态预判函数 ====================
    def calculate_early_score(self, open_price, close_prev, ma5_prev, ma20_prev):
        if ma20_prev == 0 or pd.isna(ma20_prev):
            return EARLY_SCORE_NEUTRAL
        dev_open = (open_price - ma20_prev) / ma20_prev
        dev_close = (close_prev - ma20_prev) / ma20_prev
        diff = dev_open - dev_close
        if diff > EARLY_SCORE_THRESHOLD:
            raw = EARLY_SCORE_NEUTRAL + min(1.0, (diff - EARLY_SCORE_THRESHOLD) * EARLY_SCORE_MAGNITUDE)
        elif diff < -EARLY_SCORE_THRESHOLD:
            raw = EARLY_SCORE_NEUTRAL - max(-1.0, (diff + EARLY_SCORE_THRESHOLD) * EARLY_SCORE_MAGNITUDE)
        else:
            raw = EARLY_SCORE_NEUTRAL
        return float(np.clip(raw, 0.0, 1.0))


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