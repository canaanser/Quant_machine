# -*- coding: utf-8 -*-
"""
双均线金叉策略（立即交叉响应）
（2026-08-26 小二陈：从 core/strategy.py 拆出，接口不变）
"""
import pandas as pd
import numpy as np
from config.risk_config import EARLY_SCORE_THRESHOLD, EARLY_SCORE_MAGNITUDE, EARLY_SCORE_NEUTRAL
from .base import BaseStrategy

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


