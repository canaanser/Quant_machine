# -*- coding: utf-8 -*-
"""
双腿融合策略（DualLegStrategy）：从 SimpleStrategy 衍生，抄底腿 + 趋势腿并存
=====================================================================
2026-08-28 小二陈（老板拍板方向）：
  Simple（抄底腿）吃震荡/超跌反弹，但在趋势行情（如 2026 科技主升浪）天生踏空——
  金叉区不买、买到的涨势减速就清仓、资金被阴跌票占用（dump_simple_trades 数据实锤）。
  本策略在 Simple 框架（MA5/MA20 + 加速度二阶 + 加仓节奏）上衍生出**趋势腿**，
  同一评分体系内双腿天然分区、自动接力：

    死叉区（MA5<MA20）→ 只有抄底腿打分：跌势衰竭（accel 负转正）抄底
    金叉区（MA5>MA20）→ 只有趋势腿打分：涨势加速（accel>0）顺势加仓；
                            涨势衰竭（accel 正转负）→ -1 清仓（两腿共用退出）

  复用 SimpleStrategy 的 prepare()（全历史因果特征矩阵预计算，84只10年秒级）
  与 risk_manager 风控；核心判定 _leg_score 单点实现，查表/暴力双路径共用，
  保证与暴力路径逐位一致。
"""
from .simple import SimpleStrategy
from core.lib.logger import get_logger

import numpy as np

logger = get_logger(__name__)


class DualLegStrategy(SimpleStrategy):
    """
    双腿融合策略：死叉区抄底腿 + 金叉区趋势腿。
    接口与 SimpleStrategy 完全一致（score_stocks/get_exit_signal/exit 语义不变），
    可无缝替换进 BacktestPipeline。
    """

    def _leg_score(self, curr_ma5, curr_ma20, prev_ma5, prev_ma20,
                   accel_t, accel_t1, buy_count):
        """单股单日双腿判定（唯一逻辑源，查表/暴力共用）：
        返回 (score, new_buy_count)。score: -1=清仓信号, 0=无操作, >0=买入评分。"""
        prev_diff = prev_ma5 - prev_ma20
        curr_diff = curr_ma5 - curr_ma20
        if prev_diff <= 0 and curr_diff > 0:
            buy_count = 0  # 金叉事件：新周期开始
        elif prev_diff >= 0 and curr_diff < 0:
            buy_count = 0  # 死叉事件：新周期开始

        if curr_ma5 > curr_ma20:
            # ===== 金叉区：趋势腿 =====
            if accel_t1 > 0 and accel_t < 0:
                return -1.0, buy_count  # 涨势衰竭 → 清仓（与抄底腿退出共用）
            if accel_t1 < 0 and accel_t > 0:
                # 动能重启拐点（accel 由负转正）= 回调结束确认——与抄底腿同一拐点条件，只分区。
                # 2026-08-28 修正：初版用 accel_t>0（任何加速日）信号泛滥且追高（20只诊断：
                # 6059信号/胜率49.2%），改为二阶拐点后信号精、与抄底腿对称。
                buy_count = min(buy_count + 1, 3)  # 回调结束 → 顺势加仓
                return self._compose_score(accel_t, buy_count), buy_count
            return 0.0, buy_count
        else:
            # ===== 死叉区：抄底腿（Simple 原逻辑） =====
            if accel_t1 < 0 and accel_t > 0:  # 跌势衰竭 → 抄底
                buy_count = min(buy_count + 1, 3)
                return self._compose_score(accel_t, buy_count), buy_count
            return 0.0, buy_count

    def _compose_score(self, accel, buy_count):
        """评分合成：base(加速度强度 0.1~0.8) × 档位权重 × 放大，封顶 0.9。
        与 SimpleStrategy 评分公式一致。"""
        weight = {0: 0.0, 1: 0.10, 2: 0.80, 3: 0.10}[buy_count]
        mult = {1: 1.0, 2: 2.0, 3: 2.0}[buy_count]
        base = min(0.8, max(0.1, abs(accel) * 10))
        return min(0.9, base * weight * mult)

    def _score_from_features(self, returns_df) -> dict:
        """查表路径：按日期映射到各股压缩序列（dropna 语义），双腿判定。"""
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
                continue
            if pos < self.long:
                continue

            if code not in self._buy_count:
                self._buy_count[code] = 0

            curr_ma5 = feat[pos, 0]
            curr_ma20 = feat[pos, 1]
            if np.isnan(curr_ma5) or np.isnan(curr_ma20):
                continue

            prev_ma5 = feat[pos - 1, 0]
            prev_ma20 = feat[pos - 1, 1]
            accel_t = feat[pos, 3]
            accel_t1 = feat[pos - 1, 3]

            score, new_count = self._leg_score(
                curr_ma5, curr_ma20, prev_ma5, prev_ma20,
                accel_t, accel_t1, self._buy_count[code])
            self._buy_count[code] = new_count
            if score != 0.0:
                scores[code] = score
                if self.verbose:
                    logger.debug(f"   📍 {code}: 双腿评分={score:.3f} (档位={new_count})")
        return scores

    def _score_bruteforce(self, returns_df) -> dict:
        """暴力路径（未 prepare 时兜底，双腿判定，与查表路径共用 _leg_score）。"""
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

            slope_t = ma5.iloc[-1] - ma5.iloc[-2]
            slope_t1 = ma5.iloc[-2] - ma5.iloc[-3]
            slope_t2 = ma5.iloc[-3] - ma5.iloc[-4]
            accel_t = slope_t - slope_t1
            accel_t1 = slope_t1 - slope_t2

            score, new_count = self._leg_score(
                ma5.iloc[-1], ma20.iloc[-1], ma5.iloc[-2], ma20.iloc[-2],
                accel_t, accel_t1, self._buy_count[code])
            self._buy_count[code] = new_count
            if score != 0.0:
                scores[code] = score
        return scores
