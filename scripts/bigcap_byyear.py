# -*- coding: utf-8 -*-
"""分年稳健性: 纯筹码买点 + 峰顶跟踪卖点(P), 大票池各年独立(2026-09-06)
每年从现金起步独立跑, 看是不是某一年撑起来的(防"一波行情拟合")
窗口: 2024全年 / 2025全年 / 2026-01~09 / 2024-2026整体
"""
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import numpy as np
from core.data_loader.freestockdb import fetch_daily_qfq_single

PNL_MIN, RETREAT, STALL = 0.30, 0.98, 15


def sim_window(df, w0, w1):
    ca = df["close"].values
    la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    dates = [d.strftime("%Y%m%d") for d in df.index]
    n = len(df)
    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    cash, shares, entry_px = 1.0, 0.0, None
    hold_hi, hold_hi_days = 0.0, 0
    for i in range(n):
        t = tv[i]
        if t > 0 and ha[i] > 0:
            tt = min(t / 100.0, 0.8)
            chip *= (1 - tt)
            m = (bins >= la[i] - 1e-9) & (bins <= ha[i] + 1e-9)
            if m.any():
                chip[m] += tt / m.sum()
        s = chip.sum()
        if s <= 0:
            continue
        cnorm = chip / s
        p = ca[i]
        d = dates[i]
        if not (w0 <= d <= w1):
            continue
        if shares > 0:
            if p > hold_hi:
                hold_hi = p; hold_hi_days = 0
            else:
                hold_hi_days += 1
            pnl = p / entry_px - 1
            sell = False
            if pnl <= -0.12:
                sell = True
            elif pnl >= PNL_MIN:
                if hold_hi_days >= STALL:
                    sell = True
                elif p < hold_hi * RETREAT and hold_hi_days >= 5:
                    sell = True
            if sell:
                cash += shares * p
                shares = 0.0; entry_px = None
                hold_hi = 0.0; hold_hi_days = 0
        else:
            trap = cnorm[bins > p].sum() * 100
            bot5 = cnorm[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if trap >= 60 and 5 <= bot5 <= 20:
                shares = cash / p
                cash = 0.0
                entry_px = p
                hold_hi = p; hold_hi_days = 0
    if shares > 1e-9 and n > 0:
        cash += shares * ca[-1]
    return cash


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    step = max(1, len(big) // 250)
    sample = big[::step][:250]
    print(f"采样 {len(sample)} 只大票(≥300亿) | P峰顶(盈30/回落2%/滞涨15) 分年独立", flush=True)
    dfs = {}
    t0 = time.time()
    for k, code in enumerate(sample):
        dfs[code] = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
        if (k + 1) % 100 == 0:
            print(f"  拉数 {k+1}/{len(sample)} 耗时{time.time()-t0:.0f}s", flush=True)
    windows = [("2024全年", "20240101", "20241231"),
               ("2025全年", "20250101", "20251231"),
               ("2026至9月", "20260101", "20260903"),
               ("2024-2026", "20240101", "20260903")]
    print(f"\n{'窗口':<10}{'几何均':>8}{'中位':>7}{'盈利':>7}{'均>2x':>7}")
    for nm, w0, w1 in windows:
        navs = []
        for code in sample:
            df = dfs[code]
            if df is None or len(df) < 500:
                continue
            navs.append(sim_window(df, w0, w1))
        g = np.array(navs, dtype=float)
        geo = float(np.exp(np.mean(np.log(np.clip(g, 1e-9, None)))))
        print(f"{nm:<10}{geo:8.3f}{np.median(g):7.2f}{np.mean(g>1)*100:6.0f}%"
              f"{np.mean(g>2)*100:6.0f}%", flush=True)
        if nm == "2026至9月":
            ann = geo ** (365 / 246)  # 粗略年化(9个月)
            print(f"{'':10}  年化粗算 {ann:.2f}")


if __name__ == "__main__":
    main()
