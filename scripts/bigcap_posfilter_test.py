# -*- coding: utf-8 -*-
r"""位置过滤 池级验证(2026-09-06): 纯筹码买点 + 峰顶跟踪卖
对比: 无位置过滤 vs 位置≤30% vs 位置≤50%
买点: 套牢≥60% 且 5%≤底部≤20% [且 价在前120日区间<=pos_max%]
卖点: 峰顶跟踪(盈30/回落2%/滞涨15) + 防崩-12
用法(Windows cmd 权威):
    python -B scripts\bigcap_posfilter_test.py --sample 200
    python -B scripts\bigcap_posfilter_test.py --all        # 全627只
    python -B scripts\bigcap_posfilter_test.py --code 688234
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


def sim_one(df, pos_max, pe_hist_max=999.0):
    ca = df["close"].values
    la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    pe = df["pe_ttm"].values if "pe_ttm" in df.columns else None
    N = len(df)
    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    cash, shares, entry_px = 1.0, 0.0, None
    hold_hi, hold_hi_days = 0.0, 0
    nt = 0
    for i in range(N):
        t = tv[i]
        if t > 0 and ha[i] > 0:
            alpha = min(t / 100.0 * 3.0, 1.0)   # 校准 n=3
            chip *= (1 - alpha)
            m = (bins >= la[i] - 1e-9) & (bins <= ha[i] + 1e-9)
            if m.any():
                chip[m] += alpha / m.sum()
        s = chip.sum()
        if s <= 0:
            continue
        c = chip / s
        p = ca[i]
        d = str(df.index[i].date()).replace("-", "")
        if not ("20240101" <= d <= "20260904"):
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
                nt += 1
        else:
            trap = c[bins > p].sum() * 100
            bot5 = c[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if trap >= 60 and 5 <= bot5 <= 20:
                if pe_hist_max < 999 and pe is not None and i >= 750 and not np.isnan(pe[i]):
                    hist = pe[i-750:i]
                    hist = hist[~np.isnan(hist)]
                    if len(hist) > 100 and np.median(hist) > 0:
                        if pe[i] / np.median(hist) > pe_hist_max:
                            continue
                if pos_max < 100 and i >= 120:
                    w120 = ca[i - 120:i]
                    lo, hi = w120.min(), w120.max()
                    pos = (p - lo) / (hi - lo) * 100 if hi > lo else 50.0
                    if pos > pos_max:
                        continue
                shares = cash / p
                cash = 0.0
                entry_px = p
                hold_hi = p; hold_hi_days = 0
    if shares > 1e-9 and N > 0:
        cash += shares * ca[-1]
    return cash, nt


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--code", default=None)
    a = ap.parse_args()
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    if a.code:
        codes = [a.code]
    else:
        big = sorted([c for c, v in mv.items() if v and v >= 300.0])
        if a.all:
            codes = big
        else:
            step = max(1, len(big) // a.sample)
            codes = big[::step][:a.sample]
    print(f"PE估值过滤验证 | {len(codes)}只 | 2024-01~2026-09", flush=True)
    t0 = time.time()
    res = {}
    dfs = {}
    combos = []
    for ci, code in enumerate(codes):
        df = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
        if df is None or len(df) < 500:
            continue
        dfs[code] = df
        if (ci + 1) % 100 == 0:
            print(f"  拉数 {ci+1}/{len(codes)} 耗时{time.time()-t0:.0f}s", flush=True)
    combos = [("无估值过滤", 999.0), ("PE<=2x自身", 2.0), ("PE<=1.5x自身", 1.5), ("PE<=1.2x自身", 1.2)]
    for nm, cap in combos:
        arr = []
        for code in codes:
            df = dfs.get(code)
            if df is None:
                continue
            nav, _ = sim_one(df, 100.0, pe_hist_max=cap)
            arr.append(nav)
        res[nm] = np.array(arr, dtype=float)
    print(f"\n{'估值过滤(相对自身750日中位PE)':<26}{'只数':>6}{'几何均':>8}{'中位':>7}{'盈利':>7}{'P10':>6}{'P90':>7}")
    for nm, _ in combos:
        g = res[nm]
        geo = float(np.exp(np.mean(np.log(np.clip(g, 1e-9, None)))))
        print(f"{nm:<26}{len(g):>6}{geo:8.3f}{np.median(g):7.2f}{np.mean(g > 1) * 100:6.0f}%"
              f"{np.percentile(g, 10):6.2f}{np.percentile(g, 90):7.2f}", flush=True)


if __name__ == "__main__":
    main()
