# -*- coding: utf-8 -*-
"""
双均线金叉策略（立即交叉响应）
（2026-08-26 小二陈：从 core/strategy.py 拆出，接口不变）

2026-08-28 小二陈（性能优化）：
  原 score_stocks 每天对全历史重算 cumprod+rolling（O(N²)，84 只 10 年 ≈ 100 分钟）。
  MA5/MA20/斜率/加速度均为因果特征（t 时刻只依赖 ≤t 数据），改为 prepare() 一次性
  预计算全历史矩阵，回测主循环每天 O(1) 查表——语义不变（停牌日 NaN 按 fillna(0)
  即"价格不变"处理，与原逐股 dropna 语义近似）。
"""
from core.logger import get_logger

logger = get_logger(__name__)

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
    def __init__(self, short=5, long=20, verbose: bool = False,
                 quality_filter: bool = False, quality_deep: float = -0.20,
                 quality_vol: float = 0.7, quality_penalty: float = 0.2,
                 quality_pos_high: float = 0.0, quality_pos_range: float = 1.0,
                 quality_pos_boost: float = -0.50, quality_pos_trim: float = -0.20,
                 freq_filter: bool = False, bottom_confirm: bool = False):
        self.short = short
        self.long = long
        self.window = long + 1
        self.lookback = long + 1
        self._buy_count = {}
        self._score_cache_key = None
        self._score_cache_value = None
        self._prepared = False
        self.verbose = verbose
        # 事前质量评分（2026-08-28 小二陈）：
        # v1 定型：深跌<-20% + 放量>0.7 = 84只组合 857.43%/Sharpe0.58（penalty 0.1 扫描定型）
        #   = 样本外62.8%/Sharpe2.13（信号级）
        # v2（+位置硬过滤）信号级更优但组合失败（集中度灾难）→ 位置改软加权：
        #   位置软加权（老板强调"越跌越买要看价格位置"）：
        #   距250日高点 < quality_pos_boost(-50%) 大下坡 → 评分×1.3（重仓真谷底）
        #   -50%~-20% 中位 → 不变
        #   > -20% 高位刚跌 → ×0.6（轻仓试探，避免接高位飞刀）
        # 筑底确认（bottom_confirm，2026-08-28 老板强调"看筑底才买"）：
        #   深跌信号 + 近5日低点≥前5日低点（低点抬高企稳）才放行；
        #   未企稳 → 降权（避免"深跌就买"被5%铁律止损频繁打脸——买入质量决定止损可行性）
        # 不满足 v1 规则的信号评分×quality_penalty 降权（轻仓试探，不踏空）。
        self.quality_filter = quality_filter
        self.quality_deep = quality_deep
        self.quality_vol = quality_vol
        self.quality_penalty = quality_penalty
        self.quality_pos_high = quality_pos_high
        self.quality_pos_range = quality_pos_range
        self.quality_pos_boost = quality_pos_boost
        self.quality_pos_trim = quality_pos_trim
        self.bottom_confirm = bottom_confirm
        # 行情状态频率控制（2026-08-28 小二陈，老板第3点）：
        # 阴跌状态（MA20 下行 + 价格在 MA20 下方 = 反弹无力）的"跌势衰竭"多为假反弹，
        # 高频交易 → 死亡螺旋（震荡阴跌亏手续费/高买低卖）。freq_filter 开启时
        # 阴跌状态信号降权（轻仓试探），上涨/震荡状态保持频率。
        self.freq_filter = freq_filter

    def _get_position_weight(self, buy_count):
        weights = {0: 0.0, 1: 0.10, 2: 0.80, 3: 0.10}
        return weights.get(buy_count, 0.0)

    def fuse_with_patterns(self, traditional_score: float, pattern_strength: float, w: float = 0.3) -> float:
        if traditional_score < 0:
            return traditional_score
        pattern_clipped = min(1.0, max(0.0, pattern_strength))
        final = (1 - w) * traditional_score + w * pattern_clipped
        return min(1.0, max(0.0, final))

    def prepare(self, returns_df: pd.DataFrame, market_ret=None, volume=None):
        """预计算全历史因果特征（按列 dropna，语义与原暴力路径逐位一致）。
        2026-08-28 小二陈（两版修复）：
          初版用 fillna(0) 处理停牌日，滚动窗口被停牌日拉长稀释 → 金叉/死叉判定错位，
          0.1% 评分差异经 _buy_count 状态链放大成 4 倍收益差（20 只验证：211% vs 49%）。
          现改为按列 dropna（压缩序列）后 cumprod+rolling，与暴力路径完全一致；
          查表用 searchsorted 按日期映射（停牌日取最近有效交易日）。
        质量评分扩展：volume 传入时预计算 deep20/vol_ratio（同一压缩序列，pos 对齐）。"""
        self._col_pos = {code: i for i, code in enumerate(returns_df.columns)}
        self._feat_cols = []
        self._q_deep = {}
        self._q_vol = {}
        self._q_p250h = {}
        self._q_rp250 = {}
        self._q_ma20slope = {}
        self._q_bottom = {}
        for code in returns_df.columns:
            s = returns_df[code].dropna()  # 停牌日删除（原暴力路径语义）
            if len(s) < self.long + 1:
                self._feat_cols.append(None)  # 数据太短：该股永不评分
                continue
            price = (1 + s).cumprod() * 100
            ma5 = price.rolling(self.short).mean()
            ma20 = price.rolling(self.long).mean()
            slope = ma5.diff()
            accel = slope.diff()
            diff = ma5 - ma20
            feat = np.column_stack([
                ma5.to_numpy(), ma20.to_numpy(),
                slope.to_numpy(), accel.to_numpy(), diff.to_numpy(),
            ])
            self._feat_cols.append((s.index.to_numpy(), feat))
            # ---- 质量特征（同压缩序列）----
            deep20 = (price / price.shift(20) - 1).to_numpy()
            self._q_deep[code] = deep20
            vol_ratio = None
            if volume is not None and code in volume.columns:
                try:
                    v = volume[code].reindex(s.index).to_numpy(dtype=float)
                    v_series = pd.Series(v, index=s.index)
                    vr = v_series / v_series.shift(1).rolling(20).mean()
                    vol_ratio = vr.to_numpy()
                except Exception:
                    vol_ratio = None
            self._q_vol[code] = vol_ratio
            # ---- 位置特征（v2：距250日高点跌幅 + 250日区间分位，"前面大下坡/底部区域"）----
            w250 = price.rolling(250, min_periods=120)
            p250_high = w250.max()
            p250_low = w250.min()
            self._q_p250h[code] = (price / p250_high - 1).to_numpy()
            rng250 = (p250_high - p250_low).replace(0, np.nan)
            self._q_rp250[code] = ((price - p250_low) / rng250).to_numpy()
            # ---- 行情状态（freq_filter：MA20 的 5 日斜率 = 均线方向）----
            self._q_ma20slope[code] = ma20.diff(5).to_numpy()
            # ---- 筑底确认特征（2026-08-28 老板强调"看筑底才买"）----
            # 近5日最低close vs 前5日最低close：低点抬高 = 企稳迹象
            low_recent = price.rolling(5, min_periods=5).min()
            low_prev = price.rolling(10, min_periods=10).min().shift(5)
            self._q_bottom[code] = (low_recent >= low_prev).to_numpy()
        self._prepared = True

    def score_stocks(self, returns_df, market_ret):
        # 当日评分缓存：pipeline 主循环与 get_exit_signal 同一天会各调一次本方法，
        # 若重算则 _buy_count（加仓档位 10%/80%/10%）一天可能递增两次，节奏失真。
        # （2026-08-28 小二陈修复）
        cache_key = (id(returns_df), id(market_ret))
        if cache_key == self._score_cache_key:
            return self._score_cache_value

        if self._prepared:
            scores = self._score_from_features(returns_df)
        else:
            scores = self._score_bruteforce(returns_df)

        result = pd.Series(scores).sort_values(ascending=False)
        self._score_cache_key = cache_key
        self._score_cache_value = result
        return result

    def _score_from_features(self, returns_df) -> dict:
        """查表路径：按日期映射到各股压缩序列（dropna 语义，与原暴力路径逐位一致）。
        returns_df = hist_returns（完整 returns 的前缀），today = 其最后一行日期；
        停牌日经 searchsorted 取最近有效交易日（等价于原 dropna 后 iloc[-1]）。"""
        scores = {}
        today = np.datetime64(returns_df.index[-1])
        for code in returns_df.columns:
            col = self._col_pos[code]
            entry = self._feat_cols[col]
            if entry is None:
                continue
            dates, feat = entry
            pos = int(np.searchsorted(dates, today, side='right')) - 1
            if pos < 0:
                continue  # 该股首个交易日尚未到来
            if pos < self.long:
                continue  # 该股有效交易日 < long+1（等价原 len(series) < long+1 continue）

            if code not in self._buy_count:
                self._buy_count[code] = 0

            curr_ma5 = feat[pos, 0]
            curr_ma20 = feat[pos, 1]
            if np.isnan(curr_ma5) or np.isnan(curr_ma20):
                continue  # rolling 未满（等价原 len < long+1 continue）

            prev_ma5 = feat[pos - 1, 0]
            prev_ma20 = feat[pos - 1, 1]
            prev_diff = prev_ma5 - prev_ma20
            curr_diff = curr_ma5 - curr_ma20

            if prev_diff <= 0 and curr_diff > 0:
                is_golden_zone = True
                is_death_zone = False
                self._buy_count[code] = 0
                if self.verbose:
                    logger.debug(f"🔔 {code} 金叉发生，重置买入计数")
            elif prev_diff >= 0 and curr_diff < 0:
                is_golden_zone = False
                is_death_zone = True
                self._buy_count[code] = 0
                if self.verbose:
                    logger.debug(f"🔔 {code} 死叉发生，重置买入计数")
            else:
                is_golden_zone = curr_ma5 > curr_ma20
                is_death_zone = curr_ma5 < curr_ma20

            accel_t = feat[pos, 3]
            accel_t1 = feat[pos - 1, 3]

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

                    # ---- 事前质量评分过滤（2026-08-28 小二陈，v2 定型）----
                    # v2：深跌<-15% 且 放量>0.7 且（距250日高点<-50% 或 区间分位<10%）
                    # = 样本外62.8%/Sharpe2.13（84只验证）；不满足 → 降权轻仓
                    if self.quality_filter and code in self._q_deep:
                        d20 = self._q_deep[code]
                        if d20 is not None and len(d20) > pos and not np.isnan(d20[pos]):
                            ok = d20[pos] < self.quality_deep
                            vr = self._q_vol.get(code)
                            if vr is not None and len(vr) > pos and not np.isnan(vr[pos]):
                                ok = ok and vr[pos] > self.quality_vol
                            if ok:
                                # 位置软加权（2026-08-28 老板强调：越跌越买要看价格位置）：
                                # 大下坡（距250日高点<-50%）= 真谷底 → 加分重仓
                                # 高位刚跌（>-20%）→ 降权轻仓（避免接高位飞刀）
                                ph = self._q_p250h.get(code)
                                if ph is not None and len(ph) > pos and not np.isnan(ph[pos]):
                                    if ph[pos] < self.quality_pos_boost:
                                        final_score = min(0.9, final_score * 1.3)
                                    elif ph[pos] > self.quality_pos_trim:
                                        final_score = final_score * 0.6
                            if not ok:
                                final_score = final_score * self.quality_penalty

                    # ---- 筑底确认（2026-08-28 老板强调"看筑底才买"）----
                    # 深跌信号 + 近5日低点≥前5日低点（低点抬高企稳）才放行；
                    # 未企稳 → 降权轻仓（买入质量决定 5% 铁律止损的可行性——不企稳就买会被止损频繁打脸）
                    if self.bottom_confirm and code in self._q_bottom:
                        bt = self._q_bottom[code]
                        if bt is not None and len(bt) > pos and not np.isnan(bt[pos]):
                            if not bt[pos]:
                                final_score = final_score * self.quality_penalty

                    # ---- 行情状态频率控制（2026-08-28 小二陈）----
                    # 阴跌态（MA20 下行且价格<MA20，反弹无力）的衰竭信号多为假反弹
                    # → 降权轻仓，避免震荡阴跌的死亡螺旋（亏手续费/高买低卖）
                    if self.freq_filter and code in self._q_ma20slope:
                        slope5 = self._q_ma20slope[code]
                        if slope5 is not None and len(slope5) > pos and not np.isnan(slope5[pos]):
                            if slope5[pos] < 0 and curr_ma5 < curr_ma20:
                                final_score = final_score * self.quality_penalty


                    if final_score > 0.001:
                        if self.verbose:
                            logger.debug(f"   📍 买入: 第{buy_count}次, 权重={weight:.0%}, 评分={final_score:.3f}")
                        scores[code] = final_score
                    else:
                        scores[code] = 0
                else:
                    scores[code] = 0
            else:
                scores[code] = 0
        return scores

    def _score_bruteforce(self, returns_df) -> dict:
        """暴力路径（未 prepare 时兜底）：每天对全历史重算 cumprod+rolling。"""
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
                    logger.debug(f"🔔 {code} 金叉发生，重置买入计数")
            elif prev_diff >= 0 and curr_diff < 0:
                is_golden_zone = False
                is_death_zone = True
                self._buy_count[code] = 0
                if self.verbose:
                    logger.debug(f"🔔 {code} 死叉发生，重置买入计数")
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
                            logger.debug(f"   📍 买入: 第{buy_count}次, 权重={weight:.0%}, 评分={final_score:.3f}")
                        scores[code] = final_score
                    else:
                        scores[code] = 0
                else:
                    scores[code] = 0
            else:
                scores[code] = 0
        return scores

    def get_exit_signal(self, returns_df: pd.DataFrame, market_ret: pd.Series) -> dict:
        """
        SimpleStrategy 退出信号（2026-08-28 方案2：死叉带强度/位置信息，真假由封控层判）
        返回 {symbol: {'exit': bool, 'strength': float, 'pct_250d_high': float}}：
          exit: 评分<-0.05 触发死叉卖出候选
          strength: 死叉强度（评分负的程度 0~1，越大越强）
          pct_250d_high: 距250日高点（<0 深跌低位；供封控层判"疑似底背离"）
        """
        scores = self.score_stocks(returns_df, market_ret)
        out = {}
        for sym, s in scores.items():
            exit_flag = s < -0.05
            # 死叉强度 = 价格 MA5/MA20 距离（2026-08-29 老板：弱死叉=均线粘合小反转，强死叉=均线张开）
            # 用价格序列（收益率 MA 均值≈0 无区分）；量级 0.01~0.05（1%-5%均线距离）
            strength = 0.0
            try:
                r = returns_df[sym].dropna()
                if len(r) >= 20:
                    price = (1 + r).cumprod()
                    ma5 = price.rolling(5).mean()
                    ma20 = price.rolling(20).mean()
                    base = abs(ma20.iloc[-1]) or 1e-9
                    strength = float(abs(ma5.iloc[-1] - ma20.iloc[-1]) / base)
            except Exception:
                strength = 0.0
            # 位置：距 250 日高点（收益率序列累计算价格）
            p250h = None
            try:
                r = returns_df[sym].dropna()
                if len(r) >= 250:
                    price = (1 + r).cumprod()
                    p250h = float(price.iloc[-1] / price.iloc[-250:].max() - 1)
                elif len(r) > 0:
                    price = (1 + r).cumprod()
                    p250h = float(price.iloc[-1] / price.max() - 1)
            except Exception:
                p250h = None
            out[sym] = {'exit': exit_flag, 'strength': strength, 'pct_250d_high': p250h}
        return out

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
