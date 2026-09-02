# -*- coding: utf-8 -*-
"""
趋势线检测（2026-08-30 老板：做了 demo 画出来看）
===================================================
经典摆动点法（v3）：
  1. fractal 找 pivot high/low（左右各 k 根 K 线内的极值）
  2. 候选线：同类 pivot 两两连线（上升线用 pivot low，下降线用 pivot high）
  3. 评分（两点定线、后续点确认）：
     - 触碰 = 锚点之间 + 锚点之后 的同类 pivot 贴近线（touch_pct 内）才计数
     - 中间点不强制贴合（真实画线允许轻微摆动）
     - 大幅破位（> break_pct）→ 线在此截断（不再延伸），但不算整线作废
  4. 有效线：触碰数 ≥ min_touches（含两端锚点，默认 3 = 两点定线第三点确认）

干湿分离：纯算法，只吃 OHLC DataFrame，吐线段 dict；画图归 utils/kline_plotter。
"""
from typing import Dict, List

import numpy as np
import pandas as pd


def _find_pivots(df: pd.DataFrame, k: int = 5) -> Dict[str, List[int]]:
    """fractal 摆动点：返回 {'high': [idx...], 'low': [idx...]}
    pivot high: high[i] 是 [i-k, i+k] 内的最大值（严格）
    pivot low : low[i]  是 [i-k, i+k] 内的最小值（严格）
    """
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    n = len(df)
    ph, pl = [], []
    for i in range(k, n - k):
        hi, lo = high[i], low[i]
        if hi == hi and all(hi >= high[i - k:i]) and all(hi > high[i + 1:i + k + 1]):
            ph.append(i)
        if lo == lo and all(lo <= low[i - k:i]) and all(lo < low[i + 1:i + k + 1]):
            pl.append(i)
    return {'high': ph, 'low': pl}


def _line_val(x0: int, y0: float, x1: int, y1: float, x: int) -> float:
    """两点确定的直线在 x 处的值（x 为行号）"""
    if x1 == x0:
        return y0
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def _collect(df: pd.DataFrame, pivots: List[int], kind: str,
             touch_pct: float, min_touches: int, min_span: int,
             max_span: int, break_pct: float) -> List[dict]:
    """对某类 pivot 两两连线并验证，返回合格线段。
    kind='low' → 上升支撑线（用 pivot low 触碰）；kind='high' → 下降压力线（用 pivot high 触碰）
    """
    if kind == 'low':
        price_col, want_slope = 'low', 'up'
    else:
        price_col, want_slope = 'high', 'down'
    prices = df[price_col].to_numpy(dtype=float)
    n = len(df)

    lines = []
    m = len(pivots)
    for a in range(m - 1):
        i0 = pivots[a]
        for b in range(a + 1, m):
            i1 = pivots[b]
            if i1 - i0 < min_span or i1 - i0 > max_span:
                continue
            y0, y1 = prices[i0], prices[i1]
            if np.isnan(y0) or np.isnan(y1) or y0 <= 0 or y1 <= 0:
                continue
            slope = (y1 - y0) / (i1 - i0)
            if want_slope == 'up' and slope <= 0:
                continue
            if want_slope == 'down' and slope >= 0:
                continue

            touches = [i0, i1]
            cut = n  # 破位截断点（默认画到图末）
            broken = False
            for p in pivots:
                if p <= i0:
                    continue
                if p < i1:
                    # 中间点：贴近则计数；轻微偏离忽略；大幅偏离 → 此组合不可靠
                    lv = _line_val(i0, y0, i1, y1, p)
                    if lv <= 0:
                        broken = True
                        break
                    if abs(prices[p] - lv) / lv <= touch_pct:
                        touches.append(p)
                    continue
                # 锚点之后：贴近=触碰；大幅破位=线到此截断
                lv = _line_val(i0, y0, i1, y1, p)
                if lv <= 0:
                    broken = True
                    break
                dev = abs(prices[p] - lv) / lv
                if dev <= touch_pct:
                    touches.append(p)
                elif dev > break_pct:
                    cut = min(cut, p)
                    broken = True
                    break
            if broken:
                continue
            if len(touches) < min_touches:
                continue

            x_end = cut - 1 if cut < n else n - 1
            if x_end < i1:
                continue
            y_end = _line_val(i0, y0, i1, y1, x_end)
            lines.append({
                'type': 'up' if want_slope == 'up' else 'down',
                'x0': i0, 'y0': float(y0),
                'x1': i1, 'y1': float(y1),
                'x_end': x_end, 'y_end': float(y_end),
                'slope': float(slope),
                'touches': len(touches),
                'touch_idx': sorted(touches),
            })
    return lines


def detect_trendlines(df: pd.DataFrame, k: int = 5, touch_pct: float = 0.02,
                      min_touches: int = 3, min_span: int = 15,
                      max_span: int = 250, break_pct: float = 0.08,
                      max_lines: int = 4) -> List[dict]:
    """主入口：输入 OHLC DataFrame（index=日期，列含 high/low），返回合格趋势线段。

    参数:
      df         : OHLC（high/low 必须）
      k          : fractal 摆动点窗口（默认 5）
      touch_pct  : 触碰容差（默认 2%，贴近线即算一次触碰）
      min_touches: 最少触碰点数（含两端锚点，默认 3 = 两点定线第三点确认）
      min_span   : 两锚点最小跨度（根 K 线，默认 15）
      max_span   : 两锚点最大跨度（根 K 线，默认 250≈1年，防超长失真线）
      break_pct  : 破位阈值（后续 pivot 偏离线超此比例 → 线在此截断，不再延伸）
      max_lines  : 返回线段数上限（按触碰数降序）
    返回:
      [{'type','x0','y0','x1','y1','x_end','y_end','slope','touches','touch_idx'}, ...]
    """
    pivots = _find_pivots(df, k=k)
    lines = _collect(df, pivots['low'], 'low', touch_pct, min_touches, min_span, max_span, break_pct)
    lines += _collect(df, pivots['high'], 'high', touch_pct, min_touches, min_span, max_span, break_pct)
    lines.sort(key=lambda d: d['touches'], reverse=True)
    # 去冗余：两线在末端线值接近（<5%）且同为升/降 → 只留触碰最多的一条
    dedup = []
    for ln in lines:
        dup = False
        for kept in dedup:
            if ln['type'] != kept['type']:
                continue
            # 在 x_end（图末）与锚点中点处比较线值
            xm = min(ln['x_end'], kept['x_end'])
            if xm <= 0:
                continue
            v1 = _line_val(ln['x0'], ln['y0'], ln['x1'], ln['y1'], xm)
            v2 = _line_val(kept['x0'], kept['y0'], kept['x1'], kept['y1'], xm)
            if v1 > 0 and v2 > 0 and abs(v1 - v2) / v2 < 0.05:
                dup = True
                break
        if not dup:
            dedup.append(ln)
    return dedup[:max_lines]
