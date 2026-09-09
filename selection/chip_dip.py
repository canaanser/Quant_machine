# -*- coding: utf-8 -*-
"""筹码抄底信号模块（2026-09-06 老板测试机：用筹码分布代替'深跌+放量'抄底）

规则（基于85样本验证：大波段起点 = 套牢盘70-100%的谷底）：
  抄底信号 = 当日筹码"套牢盘占比高" 且 价格在底部区域 且 有企稳迹象
  具体：①套牢盘≥70%（筹码大部分被套）  ②价格距近250日低点不远(<15%)
       ③换手萎缩(恐吓尾声，<近60日中位) → 主力洗够、没人卖 = 买点
卖出：沿用金叉/死叉纪律或固定持有N日——先用最简单：涨20%止盈或跌破买入价8%止损

用法：python -B scripts/chip_dip_test.py --pool 精选15|84|direction --start 2022-01-01
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np
import json
import urllib.request
import urllib.parse
import argparse


def load_daily(code: str, y0=2018, y1=2026):
    """统一取数：Windows=SDK qfq 前复权；WSL=HTTP+折算(自检)。口径与主引擎一致。"""
    code = str(code).zfill(6)
    from core.data_loader.freestockdb import fetch_daily_qfq_single
    df = fetch_daily_qfq_single(code, f"{y0}-01-01", f"{y1}-12-31")
    out = {}
    for d, r in df.iterrows():
        out[d.strftime("%Y%m%d")] = {
            "open": r["open"], "high": r["high"], "low": r["low"],
            "close": r["close"], "volume": r["volume"], "turnover": r["turnover"],
        }
    return out


def chip_distribution(daily: dict, date: str, lookback=400, step=0.5):
    """date 当日的筹码分布（只用≤date数据，无未来函数）
    step: 价格桶步长。返回 (bins, chip_normalized)"""
    dates = sorted(d for d in daily if d <= date)[-lookback:]
    if not dates:
        return None, None
    closes = [float(daily[d]["close"]) for d in dates]
    lo_all, hi_all = min(closes), max(closes)
    bins = np.arange(max(0.5, lo_all - step * 20), hi_all + step * 20, step)
    chip = np.zeros(len(bins))
    for d in dates:
        r = daily[d]
        lo, hi = float(r["low"]), float(r["high"])
        tv = float(r["turnover"]) / 100
        chip = chip * (1 - tv)
        m = (bins >= lo) & (bins < hi)
        if m.any():
            chip[m] += tv / m.sum()
    s = chip.sum()
    if s <= 0:
        return bins, chip
    return bins, chip / s


def _d8(date): return str(date).replace('-','')

def chip_metrics(code: str, date: str, daily_cache=None):
    """返回 (套牢盘%, 获利盘%, 筹码峰, 价) — 只用历史"""
    date=_d8(date)
    daily = daily_cache if daily_cache else load_daily(code)
    bins, chip = chip_distribution(daily, date)
    if chip is None:
        return None
    px = float(daily[date]["close"])
    trap = chip[bins > px].sum() * 100
    gain = chip[bins < px].sum() * 100
    peak = bins[int(chip.argmax())]
    return dict(trap=trap, gain=gain, peak=float(peak), px=px, date=date)


def buy_signal(code: str, date: str, daily_cache=None,
               trap_min=70.0, dd_max=15.0):
    """筹码抄底信号：
    ① 套牢盘 ≥ trap_min(70%)
    ② 价距近250日低点 < dd_max(15%)
    ③ 换手 < 近60日中位（缩量企稳）
    返回 (bool, dict)"""
    date=_d8(date)
    daily = daily_cache if daily_cache else load_daily(code)
    dates = sorted(d for d in daily if d <= date)
    if len(dates) < 60:
        return False, {}
    m = chip_metrics(code, date, daily)
    if not m or m["trap"] < trap_min:
        return False, m or {}
    # 距250日低点
    win = [float(daily[d]["close"]) for d in dates[-250:]]
    lo250 = min(win)
    dd = (m["px"] / lo250 - 1) * 100
    # 换手萎缩：当日换手 < 近60日中位
    tv_now = float(daily[date]["turnover"])
    tv_hist = [float(daily[d]["turnover"]) for d in dates[-60:]]
    tv_mid = float(np.median(tv_hist))
    vol_shrink = tv_now <= tv_mid
    sig = dd <= dd_max and vol_shrink
    return sig, dict(m, dd=dd, tv=tv_now, tv_mid=tv_mid)
