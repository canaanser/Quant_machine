# -*- coding: utf-8 -*-
"""验证: 筹码独立 vs 筹码被门交集过滤（老板 2026-09-06）
采样大票, 同卖法(峰顶跟踪P)只改买点形态:
  PIND  : 纯筹码买点(套牢≥60,底5-20)               —— 独立, 无门
  P_GOLD: 纯筹码买点 ∩ MA5>MA20(金叉区才买)        —— 交集过滤(死叉门)
  P_TREND: 纯筹码买点 ∩ 价≥120日均线(趋势门)        —— 交集过滤(趋势门)
比较: 几何均/中位/盈利/笔数 → 看交集是否砍效用
"""
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import numpy as np
import pandas as pd
from core.data_loader.freestockdb import fetch_daily_qfq_single

PNL_MIN, RETREAT, STALL = 0.30, 0.98, 15


def sim_one_gate(df, gate):
    """gate: 'IND'纯筹码 / 'GOLD'∩金叉 / 'TREND'∩站上120日线"""
    ca = df["close"].values
    la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    dates = [d.strftime("%Y%m%d") for d in df.index]
    n = len(df)
    c = pd.Series(ca)
    ma5 = c.rolling(5).mean().values
    ma20 = c.rolling(20).mean().values
    ma120 = c.rolling(120).mean().values

    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)

    cash, shares, entry_px = 1.0, 0.0, None
    hold_hi, hold_hi_days = 0.0, 0
    ntrades = 0
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
        if not ("20240101" <= d <= "20260903"):
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
                ntrades += 1
        else:
            trap = cnorm[bins > p].sum() * 100
            bot5 = cnorm[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if trap >= 60 and 5 <= bot5 <= 20:
                gate_ok = True
                if gate == 'GOLD' and not (not np.isnan(ma5[i]) and not np.isnan(ma20[i]) and ma5[i] > ma20[i]):
                    gate_ok = False
                elif gate == 'TREND' and not (not np.isnan(ma120[i]) and p >= ma120[i]):
                    gate_ok = False
                if gate_ok:
                    shares = cash / p
                    cash = 0.0
                    entry_px = p
                    hold_hi = p; hold_hi_days = 0
    if shares > 1e-9 and n > 0:
        cash += shares * ca[-1]
    return cash, ntrades


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    step = max(1, len(big) // 200)
    sample = big[::step][:200]
    print(f"采样 {len(sample)} 只大票 | 卖法=峰顶跟踪(盈30/回落2%/滞涨15) | 2024-01~2026-09", flush=True)
    res = {"IND": [], "GOLD": [], "TREND": []}
    nt = {"IND": [], "GOLD": [], "TREND": []}
    t0 = time.time()
    for k, code in enumerate(sample):
        df = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
        if df is None or len(df) < 500:
            continue
        for g in res:
            nav, nn = sim_one_gate(df, g)
            res[g].append(nav)
            nt[g].append(nn)
        if (k + 1) % 50 == 0:
            print(f"  {k+1}/{len(sample)} 耗时{time.time()-t0:.0f}s", flush=True)
    print(f"\n{'形态':<28}{'几何均':>8}{'中位':>7}{'盈利':>7}{'均笔':>6}")
    labels = {
        "IND": "纯筹码独立(无门)",
        "GOLD": "筹码 ∩ 金叉区(MA5>MA20)",
        "TREND": "筹码 ∩ 站上120日线",
    }
    for g in res:
        a = np.array(res[g], dtype=float)
        geo = float(np.exp(np.mean(np.log(np.clip(a, 1e-9, None)))))
        print(f"{labels[g]:<28}{geo:8.3f}{np.median(a):7.2f}{np.mean(a>1)*100:6.0f}%"
              f"{np.mean(nt[g]):6.1f}", flush=True)


if __name__ == "__main__":
    main()
