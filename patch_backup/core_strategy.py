# core/strategy.py
# Alpha剥离策略模块（滚动OLS残差动量）
import pandas as pd
import numpy as np
from config.risk_config import EARLY_SCORE_THRESHOLD, EARLY_SCORE_MAGNITUDE, EARLY_SCORE_NEUTRAL
from statsmodels.regression.rolling import RollingOLS
import statsmodels.api as sm

class AlphaScoreStrategy:
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


class FullFitStrategy:
    def __init__(self):
        self.window = 1
        self.lookback = 1
    def score_stocks(self, returns_df, market_ret):
        scores = {code: 1.0 for code in returns_df.columns}
        return pd.Series(scores).sort_values(ascending=False)

# ==================== 双均线金叉策略 ====================
# ==================== 双均线金叉策略（高斯评分版） ====================
# ==================== 双均线金叉策略（趋势确认 + 死叉卖出） ====================
# ==================== 斜率拐点 + 死叉双重清仓策略 ====================
# ==================== 区间状态 + 斜率变化率策略 ====================
# ==================== 区间状态 + 斜率变化率 + 交叉确认策略 ====================
# ==================== 区间状态 + 斜率变化率 + 交叉确认 + 确认天数 ====================
# ==================== 区间状态 + 斜率变化率 + 交叉确认（1天确认） ====================
# ==================== 立即交叉响应策略 ====================
# ==================== 临近交叉合并策略 ====================
# ==================== 最优买入分布策略 ====================
# ==================== 动态长周期检测策略 ====================
# ==================== 整合策略：容差 + 动态长周期 ====================
# ==================== 调整后的整合策略 ====================
# ==================== 立即交叉响应策略（最小二乘法之前的版本） ====================
# ==================== 离散相位策略 ====================
# ==================== 动态仓位分配策略 ====================
# ==================== 完整策略：动态仓位 + 保护期 ====================
# ==================== 最终策略：80%仓位集中在第二次 ====================
# ==================== 熊市因子增强策略 ====================
# ==================== 熊市因子增强策略 ====================
# ==================== 单向建仓策略 ====================
# ==================== 动态市场模式策略 ====================
# ==================== 立即交叉响应策略（带大盘过滤） ====================
# ==================== 立即交叉响应策略（带仓位分配 + 大盘过滤） ====================
# ==================== 纯策略版本（无大盘因子） ====================
# ==================== 立即交叉响应策略（带仓位分配 + 大盘过滤） ====================
# ==================== 立即交叉响应策略（带仓位分配） ====================
# ==================== 立即交叉响应策略（权重互换版） ====================
class SimpleStrategy:
    """
    双均线金叉策略（立即交叉响应）：
    - 金叉/死叉发生当天立即切换区间
    - 仓位分配：第1次10%（评分放大1倍），第2次80%（评分放大2倍），第3次10%（评分放大2倍）
    """
    def __init__(self, short=5, long=20):
        self.short = short
        self.long = long
        self.window = long + 1
        self.lookback = long + 1
        self._buy_count = {}

    def _get_position_weight(self, buy_count):
        weights = {0: 0.0, 1: 0.10, 2: 0.80, 3: 0.10}
        return weights.get(buy_count, 0.0)

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
                print(f"🔔 {code} 金叉发生，重置买入计数")
            elif prev_diff >= 0 and curr_diff < 0:
                is_golden_zone = False
                is_death_zone = True
                self._buy_count[code] = 0
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
                    
                    # ======== 互换第1次和第3次的评分放大系数 ========
                    buy_count = self._buy_count[code]
                    if buy_count == 1:
                        # 第1次：放大1倍（原来是2倍）
                        final_score = base_score * weight * 1.0
                    elif buy_count == 2:
                        # 第2次：放大2倍（不变）
                        final_score = base_score * weight * 2.0
                    elif buy_count == 3:
                        # 第3次：放大2倍（原来是1倍）
                        final_score = base_score * weight * 2.0
                    else:
                        final_score = 0.0
                    
                    final_score = min(0.9, final_score)
                    
                    if final_score > 0.001:
                        print(f"   📍 买入: 第{buy_count}次, 权重={weight:.0%}, 评分={final_score:.3f}")
                        scores[code] = final_score
                    else:
                        scores[code] = 0
                else:
                    scores[code] = 0
            else:
                scores[code] = 0
                
        return pd.Series(scores).sort_values(ascending=False)

class TrendStrategy:
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
