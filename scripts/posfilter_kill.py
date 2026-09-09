# -*- coding: utf-8 -*-
"""位置过滤误杀分析: 列出被滤掉的赚单(2026-09-06 老板)
对采样票: replay 无过滤(收全部单) vs pos<=30%(收部分单)
找出 pos<=30 下不存在、但无过滤下收益>0 的单 → 被误杀的赚单
输出按收益排序的代表性误杀单
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import numpy as np
from core.data_loader.freestockdb import fetch_daily_qfq_single

PNL_MIN, RETREAT, STALL = 0.30, 0.98, 15


def sim_trades(df, pos_max):
    """返回每笔 (buy_d, buy_px, sell_d, sell_px, ret%)"""
    ca = df["close"].values
    la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    N = len(df)
    hi_max = float(ha.max()); w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    cash, shares, entry_px, entry_d = 1.0, 0.0, None, None
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
        d = str(df.index[i].date()).replace("-", "")
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
                tr.append((entry_d, float(entry_px), d, float(p), pnl * 100))
                shares = 0.0; entry_px = None; hold_hi = 0; hhd = 0
        else:
            trap = c[bins > p].sum() * 100
            bot5 = c[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if trap >= 60 and 5 <= bot5 <= 20:
                if pos_max < 100 and i >= 120:
                    w120 = ca[i - 120:i]
                    lo, hi = w120.min(), w120.max()
                    if (p - lo) / (hi - lo) * 100 > pos_max if hi > lo else False:
                        continue
                shares = cash / p
                cash = 0.0
                entry_px = p; entry_d = d
                hold_hi = p; hhd = 0
    return tr


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    # 取 40 只有代表性的(随机+市值分层), 够找出误杀单即可
    rng = np.random.default_rng(3)
    codes = sorted(rng.choice(big, size=40, replace=False))
    print(f"采样 {len(codes)} 只, 找位置过滤误杀的赚单...", flush=True)
    killed = []  # (code, buy_d, buy_px, ret, pos)
    for code in codes:
        df = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
        if df is None or len(df) < 500:
            continue
        full = sim_trades(df, 100)
        filt = sim_trades(df, 30)
        fset = {(t[0], round(t[1], 2)) for t in filt}
        for t in full:
            if (t[0], round(t[1], 2)) not in fset and t[4] > 5:
                # 计算该买入位置
                d = t[0]
                idx = int(np.where(np.array([str(x.date()).replace("-", "") for x in df.index]) == d)[0][0])
                ca = df["close"].values
                w120 = ca[max(0, idx - 120):idx]
                lo, hi = w120.min(), w120.max()
                pos = (t[1] - lo) / (hi - lo) * 100 if hi > lo else 50
                killed.append((code, t[0], t[1], t[4], pos))
    killed.sort(key=lambda x: -x[3])
    print(f"\n位置≤30% 误杀的赚单(收益>5%): {len(killed)} 笔\n")
    print(f"{'代码':<8}{'买入日':<10}{'买价':>8}{'收益':>8}{'位置%':>7}")
    for code, bd, bp, ret, pos in killed[:30]:
        print(f"{code:<8}{bd:<10}{bp:>8.2f}{ret:>+7.1f}%{pos:>6.0f}%")


if __name__ == "__main__":
    main()
