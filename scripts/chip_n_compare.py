# -*- coding: utf-8 -*-
"""筹码算法重跑对比: n=1(旧) vs n=3(新校准贴近东财) 2026-09-06
同一策略: 纯筹码买点(套牢≥60, 底5-20%) + 峰顶跟踪卖(盈30/回落2%/滞涨15) + 防崩12
大票池采样200, 2024-01~2026-09
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


def sim_one(df, n_coef, spread='avg'):
    ca = df["close"].values
    la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    dates = [d.strftime("%Y%m%d") for d in df.index]
    N = len(df)
    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    cash, shares, entry_px = 1.0, 0.0, None
    hold_hi, hold_hi_days = 0.0, 0
    ntrade = 0
    for i in range(N):
        t = tv[i]
        if t > 0 and ha[i] > 0:
            alpha = min(t / 100.0 * n_coef, 1.0)   # 通达信: 换手率×衰减系数
            chip *= (1 - alpha)
            if spread == 'avg':
                m = (bins >= la[i] - 1e-9) & (bins <= ha[i] + 1e-9)
                if m.any():
                    chip[m] += alpha / m.sum()
            else:  # tripk: low-high 间以收盘价为顶点的三角(通达信'平均价'形态, 紫光实证)
                a, b, v = la[i], ha[i], ca[i]
                if not (a <= v <= b):
                    v = (a + b) / 2
                x = bins[(bins >= a - 1e-9) & (bins <= b + 1e-9)]
                if len(x):
                    tri = np.where(x <= v, (x - a) / (v - a + 1e-9), (b - x) / (b - v + 1e-9))
                    tri = np.clip(tri, 0, None)
                    tri = tri / (tri.sum() + 1e-12)
                    chip[(bins >= a - 1e-9) & (bins <= b + 1e-9)] += alpha * tri
        s = chip.sum()
        if s <= 0:
            continue
        c = chip / s
        p = ca[i]
        d = dates[i]
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
                ntrade += 1
        else:
            trap = c[bins > p].sum() * 100
            bot5 = c[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if trap >= 60 and 5 <= bot5 <= 20:
                shares = cash / p
                cash = 0.0
                entry_px = p
                hold_hi = p; hold_hi_days = 0
    if shares > 1e-9 and N > 0:
        cash += shares * ca[-1]
    return cash, ntrade


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    step = max(1, len(big) // 200)
    sample = big[::step][:200]
    print(f"采样 {len(sample)} 大票 | 纯筹码买+峰顶卖 | n=1旧 vs n=3新 | 2024-01~2026-09", flush=True)
    combos = {"旧 n1/均摊": (1, 'avg'), "新 n1/收顶三角": (1, 'tripk'), "新 n3/收顶三角": (3, 'tripk')}
    res = {k: [] for k in combos}
    nt = {k: [] for k in combos}
    t0 = time.time()
    for ci, code in enumerate(sample):
        df = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
        if df is None or len(df) < 500:
            continue
        for k, (n, sp) in combos.items():
            nav, nn = sim_one(df, n, sp)
            res[k].append(nav)
            nt[k].append(nn)
        if (ci + 1) % 50 == 0:
            print(f"  {ci+1}/{len(sample)} 耗时{time.time()-t0:.0f}s", flush=True)
    print(f"\n{'筹码算法':<16}{'几何均':>8}{'中位':>7}{'盈利':>7}{'均笔':>6}{'P90':>7}")
    for k in combos:
        a = np.array(res[k], dtype=float)
        geo = float(np.exp(np.mean(np.log(np.clip(a, 1e-9, None)))))
        print(f"{k:<20}{geo:8.3f}{np.median(a):7.2f}{np.mean(a>1)*100:6.0f}%"
              f"{np.mean(nt[k]):6.1f}{np.percentile(a,90):7.2f}", flush=True)


if __name__ == "__main__":
    main()
