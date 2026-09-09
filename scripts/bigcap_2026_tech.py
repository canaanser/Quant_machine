# -*- coding: utf-8 -*-
"""2026年分年: 科技成长 vs 传统老登 收益对比(2026-09-06 老板猜想)
采样大票, 2026-01-01~2026-09-04, 纯筹码买(n=3)+峰顶跟踪卖
每只记录收益+申万一级行业 → 分组: 科技(电子/计算机/通信/军工/电力设备/机械) vs 传统(其余)
"""
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "3rdpart_pybao"))
import numpy as np
from core.data_loader.freestockdb import fetch_daily_qfq_single

PNL_MIN, RETREAT, STALL = 0.30, 0.98, 15
TECH = {"电子", "计算机", "通信", "国防军工", "电力设备", "机械设备"}


def sim_one(df):
    ca = df["close"].values
    la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    N = len(df)
    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    cash, shares, entry_px = 1.0, 0.0, None
    hold_hi, hhd = 0.0, 0
    for i in range(N):
        t = tv[i]
        if t > 0 and ha[i] > 0:
            alpha = min(t / 100.0 * 3.0, 1.0)
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
        if not ("20260101" <= d <= "20260904"):
            continue
        if shares > 0:
            if p > hold_hi:
                hold_hi = p; hhd = 0
            else:
                hhd += 1
            pnl = p / entry_px - 1
            sell = False
            if pnl <= -0.12:
                sell = True
            elif pnl >= PNL_MIN:
                if hhd >= STALL:
                    sell = True
                elif p < hold_hi * RETREAT and hhd >= 5:
                    sell = True
            if sell:
                cash += shares * p
                shares = 0.0; entry_px = None
                hold_hi = 0.0; hhd = 0
        else:
            trap = c[bins > p].sum() * 100
            bot5 = c[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if trap >= 60 and 5 <= bot5 <= 20:
                shares = cash / p
                cash = 0.0
                entry_px = p
                hold_hi = p; hhd = 0
    if shares > 1e-9 and N > 0:
        cash += shares * ca[-1]
    return cash


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    step = max(1, len(big) // 300)
    sample = big[::step][:300]
    print(f"采样 {len(sample)} 大票 | 2026-01~2026-09 | 拉行业...", flush=True)
    # 行业映射
    inds = {}
    try:
        from stock_sdk import bk
        inds = bk.get(sample, 1, "name") or {}
    except Exception as e:
        print("行业获取失败", e)
    t0 = time.time()
    res = []
    for ci, code in enumerate(sample):
        df = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
        if df is None or len(df) < 500:
            continue
        nav = sim_one(df)
        ind = (inds.get(code) or ["?"])[0]
        res.append((code, nav, ind))
        if (ci + 1) % 100 == 0:
            print(f"  {ci+1}/{len(sample)} 耗时{time.time()-t0:.0f}s", flush=True)
    # 输出分组
    tech = [(c, n, i) for c, n, i in res if i in TECH]
    trad = [(c, n, i) for c, n, i in res if i not in TECH]
    def stat(grp, nm):
        g = np.array([x[1] for x in grp], dtype=float)
        geo = float(np.exp(np.mean(np.log(np.clip(g, 1e-9, None)))))
        print(f"\n[{nm}] {len(grp)}只 几何均{geo:.3f} ({(geo-1)*100:+.0f}%) 中位{np.median(g):.2f} "
              f"盈利{(g>1).mean()*100:.0f}%")
    print("\n===== 2026年(1-9月) 纯筹码+峰顶跟踪 =====")
    stat(tech, "科技成长(电子/计算机/通信/军工/电力设备/机械)")
    stat(trad, "传统老登(其余)")
    print("\n--- 科技组明细(按收益) ---")
    for c, n, i in sorted(tech, key=lambda x: -x[1])[:15]:
        print(f"  {c} [{i}] {(n-1)*100:+7.1f}%")
    print("--- 科技组最差 ---")
    for c, n, i in sorted(tech, key=lambda x: x[1])[:8]:
        print(f"  {c} [{i}] {(n-1)*100:+7.1f}%")
    print("\n--- 传统组最好 ---")
    for c, n, i in sorted(trad, key=lambda x: -x[1])[:10]:
        print(f"  {c} [{i}] {(n-1)*100:+7.1f}%")
    print("--- 传统组最差 ---")
    for c, n, i in sorted(trad, key=lambda x: x[1])[:10]:
        print(f"  {c} [{i}] {(n-1)*100:+7.1f}%")


if __name__ == "__main__":
    main()
