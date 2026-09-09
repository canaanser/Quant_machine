# -*- coding: utf-8 -*-
r"""纯筹码买入 + 止盈梯度卖出（老板 2026-09-06 开干）
买点(纯筹码两维, 不掺换手/距低点): 套牢≥T 且 5%≤底部筹码≤20%
卖点(止盈梯度, 分批落袋): 每档止盈卖剩余仓位的 fraction
  默认梯度: +15%卖1/3 → +30%再卖1/2 → +50%清; 破成本-12%防崩线清剩余
对比: 固定+20%止盈(单档) vs 梯度(多档)
2024-01-01 ~ 2026-09-03 (和老板三年窗口一致)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import numpy as np
import pandas as pd

START = "20240101"
END = "20260903"
G_START = START
G_END = END


def simulate(df, trap_min, ladder, start="20240101"):
    """ladder: [(触盈幅, 卖剩余比例), ...] 升序; 最后档后剩余清仓."""
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

    cash, shares, entry_px, entry_d = 1.0, 0.0, None, None
    done_ladder = 0        # 已触发几档
    trades = []            # (buy_d, buy_px, sell_d, sell_px, reason, ret_of_that_slice)
    peak_after_buy = 0.0   # 持仓期最高价(用于梯度判断用收盘触发即可, 这里跟踪收盘)
    days_flat = 0
    for i in range(n):
        d = dates[i]
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
        p = ca[i]
        if not (START <= d <= END):
            continue
        if shares > 0:
            pnl = p / entry_px - 1
            # 防崩线: 破成本-12%清剩余(认错, 防灾难)
            if pnl <= -0.12:
                cash += shares * p
                trades.append((entry_d, entry_px, d, p, '防崩-12%', (p/entry_px-1)*100))
                shares = 0.0; entry_px = None; done_ladder = 0
                continue
            # 止盈梯度: 用收盘价触发
            while done_ladder < len(ladder):
                tgt, frac = ladder[done_ladder]
                if pnl >= tgt:
                    sell_sh = shares * frac
                    cash += sell_sh * p
                    shares -= sell_sh
                    trades.append((entry_d, entry_px, d, p,
                                   f'盈{tgt*100:.0f}%', (p/entry_px-1)*100))
                    done_ladder += 1
                else:
                    break
            if shares <= 1e-9:
                shares = 0.0; entry_px = None; done_ladder = 0
        else:
            days_flat += 1
            cnorm = chip / s
            trap = cnorm[bins > p].sum() * 100
            bot5 = cnorm[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if trap >= trap_min and 5 <= bot5 <= 20:
                shares = cash / p
                cash = 0.0
                entry_px = p; entry_d = d
                done_ladder = 0
    if shares > 1e-9 and n > 0:
        p = ca[-1]
        cash += shares * p
        trades.append((entry_d, entry_px, dates[-1], p, '期末', (p/entry_px-1)*100))
    return cash, trades


def main():
    from core.data_loader.freestockdb import fetch_daily_qfq_single
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="000063")
    ap.add_argument("--trap", type=float, default=0.60)
    args = ap.parse_args()
    df = fetch_daily_qfq_single(args.code, "2021-01-01", "2026-12-31")
    print(f"{args.code} 纯筹码买入(套牢≥{args.trap:.0%},底部5-20%) 卖法: 止盈梯度 vs 固定  | {START}~{END}\n")
    ladders = {
        "固定+20%": [(0.20, 1.0)],
        "梯15/30/50": [(0.15, 1/3), (0.30, 0.5), (0.50, 1.0)],
        "梯10/20/35": [(0.10, 1/3), (0.20, 0.5), (0.35, 1.0)],
        "梯20/40拿": [(0.20, 0.4), (0.40, 1.0)],
    }
    for nm, lad in ladders.items():
        cash, trades = simulate(df, args.trap, lad)
        nav = cash
        rets = np.array([t[5] for t in trades]) if trades else np.array([])
        wins = len([r for r in rets if r > 0])
        slices = len(trades)
        print(f"[{nm}] 期末净值 {nav:.3f} ({(nav-1)*100:+.0f}%) | 卖{len(trades)}次 "
              f"盈{len([t for t in trades if t[4].startswith('盈') or t[4]=='期末' and t[5]>0])}"
              f" 防崩{len([t for t in trades if t[4]=='防崩-12%'])}")
    # 明细打印: 用一个梯度
    print("\n--- 梯15/30/50 逐次卖出 ---")
    _, trades = simulate(df, args.trap, ladders["梯15/30/50"])
    for t in trades:
        print(f"  买{t[0]}@{t[1]:.2f} → 卖{t[2]}@{t[3]:.2f} {t[4]} 该笔{t[5]:+.1f}%")


if __name__ == "__main__":
    main()
