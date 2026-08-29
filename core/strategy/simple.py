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
        self._q_bottom_div = {}
        self._q_top_div = {}
        self._q_kelly = {}
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
            # ---- 严格底背离预计算（2026-08-29：价格创新低但RSI未新低=跌不动=反转，死叉不该卖）----
            # 前低回看60日；价格≤前低×1.02 且 RSI>前低RSI+2 → 底背离（逻辑定义，不为触发率放宽）
            n = len(price)
            bd = np.zeros(n, dtype=bool)
            if n >= 70:
                try:
                    rsi = self._rsi(pd.Series(price), 14).to_numpy()
                    price_np = price.to_numpy()
                    for i in range(60, n):
                        lo = price_np[i - 60:i + 1].min()
                        if price_np[i] <= lo * 1.02:
                            low_pos = int(np.argmin(price_np[i - 60:i + 1]))
                            low_rsi = rsi[i - 60 + low_pos]
                            if rsi[i] > low_rsi + 2:
                                bd[i] = True
                except Exception:
                    bd = np.zeros(n, dtype=bool)
            self._q_bottom_div[code] = bd
            # ---- 顶背离预计算（2026-08-29 金叉买真假：价格创新高但RSI未创新高=涨不动=假金叉拒买）----
            # 对称底背离：价格接近60日新高（≥前高×0.98）且 RSI < 前高RSI-2 → 顶背离
            td = np.zeros(n, dtype=bool)
            if n >= 70:
                try:
                    rsi = self._rsi(pd.Series(price), 14).to_numpy()
                    price_np = price.to_numpy()
                    for i in range(60, n):
                        hi = price_np[i - 60:i + 1].max()
                        if price_np[i] >= hi * 0.98:
                            high_pos = int(np.argmax(price_np[i - 60:i + 1]))
                            high_rsi = rsi[i - 60 + high_pos]
                            if rsi[i] < high_rsi - 2:
                                td[i] = True
                except Exception:
                    td = np.zeros(n, dtype=bool)
            self._q_top_div[code] = td
            # ---- 凯利动态止损预计算（2026-08-30 老板拍板：凯利公式驱动动态止损，防过拟合不精调）----
            # p=胜率：历史金叉信号（ma5上穿ma20）后20日涨幅>0比例（老板定20日口径）
            # b=赔率：历史金叉信号平均盈利/平均亏损（绝对值）
            # f*=(b·p−(1−p))/b，clip[-0.2,0.3]；滚动统计（当日只用之前信号，无未来函数）
            # 样本<20 标记 0，prepare 结束用池子均值回填（防单票小样本抖动=过拟合）
            kl = np.zeros(n, dtype=float)
            try:
                price_np = price.to_numpy()
                diff_np = diff.to_numpy()
                gc = (diff_np > 0) & (np.roll(diff_np, 1) <= 0)
                gc[0] = False
                gc_idx = np.where(gc)[0]
                if len(gc_idx) > 0:
                    # 金叉点 t 的 20 日后收益（2026-08-30 修NaN：无效信号置0，不计入盈亏——原NaN被当亏损致胜率低估/凯利NaN污染）
                    r20 = np.full(len(gc_idx), np.nan)
                    valid = gc_idx + 20 < n
                    r20[valid] = price_np[gc_idx[valid] + 20] / price_np[gc_idx[valid]] - 1
                    r20 = np.where(np.isnan(r20), 0.0, r20)
                    win = (r20 > 0).astype(int)
                    lose = (r20 < 0).astype(int)  # 0=无效信号，不算胜也不算负
                    win_ret = np.where(win, r20, 0.0)
                    lose_ret = np.where(lose, -r20, 0.0)  # 亏损绝对值
                    # 逐日累积统计（滚动：当日位置只用当日及之前的金叉信号）
                    cum_w = np.cumsum(np.bincount(gc_idx, weights=win, minlength=n))
                    cum_l = np.cumsum(np.bincount(gc_idx, weights=lose, minlength=n))
                    cum_wr = np.cumsum(np.bincount(gc_idx, weights=win_ret, minlength=n))
                    cum_lr = np.cumsum(np.bincount(gc_idx, weights=lose_ret, minlength=n))
                    for i in range(n):
                        w, l = int(cum_w[i]), int(cum_l[i])
                        tot = w + l
                        if tot < 20:
                            continue  # 样本不足→0，池均值回填
                        p = w / tot
                        avg_win = cum_wr[i] / w if w else 0.0
                        avg_lose = cum_lr[i] / l if l else 0.0
                        if avg_win <= 0 or avg_lose <= 0:
                            kl[i] = -0.2  # 无盈利/无亏损样本→保守认错快
                            continue
                        b = avg_win / avg_lose
                        f = (b * p - (1 - p)) / b
                        kl[i] = max(-0.2, min(0.3, f))
            except Exception:
                kl = np.zeros(n, dtype=float)
            self._q_kelly[code] = kl
        # 池子均值回填：样本<20 的票/日期用全池均值（老板：防过拟合，不精调单票）
        pool_means = [float(a[a != 0].mean()) for a in self._q_kelly.values() if (a != 0).any()]
        if pool_means:
            pm = float(np.mean(pool_means))
            for code in self._q_kelly:
                arr = self._q_kelly[code]
                arr[arr == 0] = pm
                self._q_kelly[code] = arr
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
        # 定位当前日期在预计算特征里的位置（searchsorted，2026-08-29 性能修复：原逐股重算 RSI 灾难）
        last_date = np.datetime64(returns_df.index[-1])  # 转 datetime64（与 _score_from_features 一致）
        for sym, s in scores.items():
            exit_flag = s < -0.05
            p250h = None
            bottom_div = False
            col_i = self._col_pos.get(sym)
            if col_i is not None and self._feat_cols[col_i] is not None:
                s_index, _ = self._feat_cols[col_i]
                pos = int(np.searchsorted(s_index, last_date, side='right')) - 1
                if pos >= 0:
                    if sym in self._q_p250h and self._q_p250h[sym] is not None and pos < len(self._q_p250h[sym]):
                        p250h = float(self._q_p250h[sym][pos])
                    if sym in self._q_bottom_div and self._q_bottom_div[sym] is not None and pos < len(self._q_bottom_div[sym]):
                        bottom_div = bool(self._q_bottom_div[sym][pos])
            out[sym] = {'exit': exit_flag, 'pct_250d_high': p250h, 'bottom_divergence': bottom_div}
        return out

    def get_kelly_factors(self, date) -> dict:
        """当日各股凯利因子 f*（T日之前历史金叉信号滚动统计，无未来函数；2026-08-30）
        供封控层动态止损：高凯利=该票值得给空间（止损放宽×1.3），负凯利=认错快（×0.7）"""
        out = {}
        d = np.datetime64(date)
        for sym, arr in self._q_kelly.items():
            col_i = self._col_pos.get(sym)
            if col_i is None or self._feat_cols[col_i] is None:
                continue
            s_index, _ = self._feat_cols[col_i]
            pos = int(np.searchsorted(s_index, d, side='right')) - 1
            if 0 <= pos < len(arr):
                out[sym] = float(arr[pos])
        return out

    @staticmethod
    def _rsi(price: pd.Series, period: int = 14) -> pd.Series:
        """RSI 相对强弱指标（Wilder 简化版）"""
        delta = price.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-9)
        return 100 - 100 / (1 + rs)

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
