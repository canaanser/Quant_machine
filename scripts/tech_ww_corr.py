# -*- coding: utf-8 -*-
"""科技票: 买入点前王文项(pe/pb/分红,本地能取) vs 该笔盈利 相关性(2026-09-06)
样本: 市值≥300亿 且 行业∈科技(电子/计算机/通信/军工/电力设备/机械)
窗口 2024-01~2026-09, 纯筹码买(n=3)+峰顶跟踪卖
每笔: 记 buy_pe, buy_pb, ever_div(买入日前是否分过红), ret%
输出: pe/pb 与 ret 相关系数 + 按王文分桶的收益对比
"""
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "3rdpart_pybao"))
import numpy as np
import pandas as pd
from core.data_loader.freestockdb import fetch_daily_qfq_single

PNL_MIN, RETREAT, STALL = 0.30, 0.98, 15
TECH = {"电子", "计算机", "通信", "国防军工", "电力设备", "机械设备"}


def sim_trades(df, code):
    ca = df["close"].values
    la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    pe = df["pe_ttm"].values if "pe_ttm" in df.columns else None
    pb = df["pb"].values if "pb" in df.columns else None
    dates = np.array([str(d.date()).replace("-", "") for d in df.index])
    N = len(df)
    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    cash, shares, entry_px, entry_i = 1.0, 0.0, None, None
    hold_hi, hhd = 0.0, 0
    tr = []
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
        d = dates[i]
        if not ("20240101" <= d <= "20260904"):
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
                # 记录: 买入时 pe/pb 相对该票自身历史(前750日)中位的偏离%
                def dev(arr, j, val):
                    if arr is None or j < 750 or np.isnan(val):
                        return np.nan
                    hist = arr[j-750:j]
                    hist = hist[~np.isnan(hist)]
                    med = np.median(hist) if len(hist) > 100 else np.nan
                    return (val / med - 1) * 100 if med and med > 0 else np.nan
                dpe = dev(pe, entry_i, pe[entry_i]) if pe is not None else np.nan
                dpb = dev(pb, entry_i, pb[entry_i]) if pb is not None else np.nan
                tr.append((code, dpe, dpb, pnl * 100))
                shares = 0.0; entry_px = None; hold_hi = 0; hhd = 0
        else:
            trap = c[bins > p].sum() * 100
            bot5 = c[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if trap >= 60 and 5 <= bot5 <= 20:
                shares = cash / p
                cash = 0.0
                entry_px = p; entry_i = i
                hold_hi = p; hhd = 0
    return tr


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    try:
        from stock_sdk import bk
        inds = bk.get(big, 1, "name") or {}
    except Exception:
        inds = {}
    tech = [c for c in big if (inds.get(c) or ["?"])[0] in TECH]
    step = max(1, len(tech) // 150)
    sample = tech[::step][:150]
    print(f"科技票采样 {len(sample)} (电子/计算机/通信/军工/电力设备/机械) | 2024-01~2026-09", flush=True)
    alltr = []
    t0 = time.time()
    for ci, code in enumerate(sample):
        df = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
        if df is None or len(df) < 500:
            continue
        alltr.extend(sim_trades(df, code))
        if (ci + 1) % 50 == 0:
            print(f"  {ci+1}/{len(sample)} 耗时{time.time()-t0:.0f}s", flush=True)
    A = pd.DataFrame(alltr, columns=["code", "pe", "pb", "ret"])  # pe/pb = 偏离%
    n = len(A)
    print(f"\n科技票共 {n} 笔买入\n")
    # pe/pb 与 ret 相关
    print("[偏离% = (买入PE / 该票前750日中位PE - 1)*100]  负数=比自身历史便宜, 正数=比自身历史贵")
    for col, nm in [("pe", "PE偏离%"), ("pb", "PB偏离%")]:
        sub = A.dropna(subset=[col])
        if len(sub) > 30:
            corr = np.corrcoef(sub[col], sub["ret"])[0, 1]
            print(f"[{nm}] 与收益相关 n={len(sub)} corr={corr:+.3f}")
    sub = A.dropna(subset=["pe", "pb"])
    if len(sub) > 50:
        sub["ww"] = sub["pe"] + sub["pb"]
        sub["bin"] = pd.qcut(sub["ww"], 4, labels=["便宜很多", "便宜些", "贵些", "贵很多"])
        print(f"\n[按 PE/PB 相对自身历史偏离分桶 → 平均收益]")
        g = sub.groupby("bin", observed=True)["ret"].agg(["count", "mean", "median"])
        print(g)


if __name__ == "__main__":
    main()
