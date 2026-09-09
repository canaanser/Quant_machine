# -*- coding: utf-8 -*-
"""
趋势线状态预计算（2026-08-30 老板：做法二/三——趋势线当买入过滤器）
====================================================================
核心：无前视 + 查表
  - 回测里每天 T 判断"今天买不买"，只能用 T 及之前的数据画线（不能偷看未来）
  - 逐日重画不可行 → 用"周/月粒度滚动检测"，预计算成 {code: Series(bool)}，回测查表

做法二（本文件主函数）：周线趋势过滤
  每周五收盘后，用截至该周的周线检测上升趋势线；
  本周收盘价站在"触碰最多的有效上升线"上方 → 允许买（True），否则禁买（False）。

做法三（同文件多级打分）：月线+周线+日线 各自判"价在主要趋势线上方"
  打分 0~3（几级在上），≥ threshold 才允许买——由 pipeline 消费。
"""
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .detector import detect_trendlines


# ---------- 周/月重采样 ----------
def resample_ohlc(daily: pd.DataFrame, freq: str = 'W-FRI') -> pd.DataFrame:
    """日线 → 周期线（OHLC 聚合）。daily index 必须为 DatetimeIndex 且含 high/low/close"""
    wk = daily.resample(freq).agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last',
    }).dropna(subset=['close'])
    return wk


# ---------- 单期判定 ----------
def _period_state(ohlc_period: pd.DataFrame, min_bars: int = 30) -> Optional[bool]:
    """用截至当前的周期线判断：当前周期收盘价是否站在主要上升趋势线上方。
    返回 True/False；数据不足或无数 → None（视为不拦截=允许，等数据够再拦）"""
    if len(ohlc_period) < min_bars:
        return None
    lines = detect_trendlines(ohlc_period, max_lines=6)
    ups = [ln for ln in lines if ln['type'] == 'up']
    if not ups:
        return False  # 没有有效上升结构 → 趋势不够格，禁买
    ups.sort(key=lambda d: d['touches'], reverse=True)
    best = ups[0]
    # 主要上升线在"当前周期"位置的值
    last_idx = len(ohlc_period) - 1
    x0, y0, x1, y1 = best['x0'], best['y0'], best['x1'], best['y1']
    if x1 == x0:
        line_val = y0
    else:
        line_val = y0 + (y1 - y0) * (last_idx - x0) / (x1 - x0)
    close_now = float(ohlc_period['close'].iloc[-1])
    # 站在支撑线上方（允许小幅贴线，-2% 容差）= 趋势向上允许买
    return close_now >= line_val * 0.98


# ---------- 滚动状态表（核心） ----------
def period_state_map(daily: pd.DataFrame, freq: str = 'W-FRI',
                     min_bars: int = 20) -> pd.Series:
    """逐周期滚动判定（无前视核心），返回**周期结束日 → 状态**的 Series。

    第 w 个周期只用第 1..w 个周期的数据检测（seg = wk.iloc[:w+1]），
    该状态在周期结束日（如周五收盘）才确定 → 回测里 T 日只能消费
    "结束日 < T" 的最近一期（由调用方 searchsorted 实现，杜绝周内偷看）。
    数据不足的早期周期 → True（放行）。
    """
    wk = resample_ohlc(daily, freq)
    states = {}
    for i in range(len(wk)):
        if i < min_bars:
            states[wk.index[i]] = True
            continue
        seg = wk.iloc[:i + 1]
        st = _period_state(seg, min_bars=min_bars)
        states[wk.index[i]] = True if st is None else st
    return pd.Series(states, name='trend_gate').sort_index()


def rolling_period_state(daily: pd.DataFrame, freq: str = 'W-FRI',
                         min_bars: int = 20, verbose: bool = False) -> pd.Series:
    """周期状态前向填充到日线（绘图/展示用；回测请用 period_state_map + 严格查询）"""
    s = period_state_map(daily, freq=freq, min_bars=min_bars)
    out = s.reindex(daily.index, method='ffill')
    out = out.where(out.notna(), True)  # 避免 fillna 弃用警告（pandas 3.0）
    return out.astype(bool)


# ---------- 多级共振打分（做法三） ----------
def multi_level_score(daily: pd.DataFrame,
                      freqs=('ME', 'W-FRI', 'D'),
                      min_bars: int = 20) -> pd.Series:
    """月/周/日 三级各自判"价在主要上升趋势线上方"，打分 0~3。
    返回与日线 index 对齐的 int Series（3=全级别向上，0=全级别向下）。
    """
    scores = pd.Series(0, index=daily.index, dtype=int)
    for freq in freqs:
        if freq == 'D':
            gate = daily_close_gate(daily, min_bars=min_bars)
        else:
            gate = rolling_period_state(daily, freq=freq, min_bars=min_bars)
        scores += gate.astype(int)
    return scores


def daily_close_gate(daily: pd.DataFrame, min_bars: int = 40) -> pd.Series:
    """日线级别：今日收盘站在近端上升趋势线上方（用最近 250 根日线检测）"""
    n = len(daily)
    if n < min_bars:
        return pd.Series(True, index=daily.index)
    out = pd.Series(True, index=daily.index, dtype=bool)
    # 每 5 个交易日检测一次，期间沿用（降低开销）
    for i in range(min_bars, n, 5):
        seg = daily.iloc[max(0, i - 250):i + 1]
        st = _period_state(seg, min_bars=10)
        out.iloc[i:min(n, i + 5)] = True if st is None else st
    return out


# ---------- 布林带闸（2026-09-02 老板：买卖由指标定，布林带加进来） ----------
# ⚠️ [DEPRECATED 2026-09-02] 实验结论：Squeeze 窄带才买两池都最差
#    （84池 Sharpe0.40<无门0.58，精选15 收益腰斩回撤-48.6%全场最差）。
#    波动收窄≠要涨（A股窄带后常继续跌）；布林只适合观察工具不适合买入过滤。
#    保留不删：见 docs/dev_notes/2026-09-02/README.md §九。未来换用法（带宽扩张追势/
#    上轨压力卖出参考）可复用其中 rolling 计算。
def bollinger_gate_state(daily: pd.DataFrame, window: int = 20, ndev: float = 2.0,
                         lookback: int = 250, q: float = 0.4) -> pd.Series:
    """布林带 Squeeze 闸（无前视，逐日判定）：
    - mid/upper/lower = MA20 ± 2σ（rolling 只用当日及之前 → 无未来函数）
    - bandwidth = (upper-lower)/mid：带宽越窄 = 越 Squeeze（整理末端，酝酿破位）
    - 放行条件 = 今日带宽 ≤ 近 lookback 日带宽的 q 分位（窄带期）
    逻辑（知乎文方法二）：金叉若发生在窄带期 = 整理破位启动（真信号）→ 放行；
    金叉发生在带宽宽阔期 = 高位震荡/趋势尾部（假金叉多）→ 拦截。
    返回与日线 index 对齐的 bool Series（True=放行）。数据不足的早期 → True。
    """
    close = daily['close']
    if len(close) < window + 5:
        return pd.Series(True, index=daily.index)
    mid = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = mid + ndev * std
    lower = mid - ndev * std
    bw = (upper - lower) / mid.replace(0, float('nan'))
    th = bw.rolling(lookback, min_periods=60).quantile(q)
    gate = bw <= th
    gate = gate.where(gate.notna(), True)  # 避免 fillna 弃用警告（pandas 3.0）
    return gate.astype(bool)
