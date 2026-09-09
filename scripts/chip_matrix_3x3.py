# -*- coding: utf-8 -*-
r"""三票 × 买点3档 × 卖法3档 全矩阵（老板 2026-09-06 开干）
买点: P恐慌(套牢≥85,底5-15) / W宽松(套牢≥60) / D深跌(距250日低≤5%)
卖法: A波段(+20%止盈/-10%止损) / B拿住(浮盈死叉不卖,保成本线) / C死叉即走
2024-01-01 ~ 2026-09-03, 输出每票 3x3 净值矩阵 + 买点/卖法主效应
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import numpy as np
import pandas as pd

START = "20240101"
TP, SL, HZ = 0.20, 0.10, 60
SL_BASE = 0.10


def simulate(df, buy_mode, sell_mode):
    ca = df["close"].values
    la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    dates = [d.strftime("%Y%m%d") for d in df.index]
    n = len(df)
    c = pd.Series(ca)
    ma5 = c.rolling(5).mean().values
    ma20 = c.rolling(20).mean().values
    lo250 = c.rolling(250).min().values

    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)

    trades = []
    cash, shares, entry_px, entry_d = 1.0, 0.0, None, None
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
        if not (START <= d <= "20260903"):
            continue
        if shares > 0:
            pnl = p / entry_px - 1
            sell = False
            reason = ''
            if sell_mode == 'A':
                if p >= entry_px * (1 + TP):
                    sell, reason = True, '止盈'
                elif p <= entry_px * (1 - SL):
                    sell, reason = True, '止损'
            elif sell_mode == 'B':
                sl_line = entry_px * (1 - SL_BASE)
                if p <= sl_line:
                    sell, reason = True, '止损'
                elif i > 1 and not np.isnan(ma5[i]) and not np.isnan(ma20[i]) \
                        and ma5[i-1] >= ma20[i-1] and ma5[i] < ma20[i] and pnl <= 0:
                    sell, reason = True, '死叉'  # B: 浮盈死叉不卖
            elif sell_mode == 'C':
                if p <= entry_px * (1 - SL_BASE):
                    sell, reason = True, '止损'
                elif i > 1 and not np.isnan(ma5[i]) and not np.isnan(ma20[i]) \
                        and ma5[i-1] >= ma20[i-1] and ma5[i] < ma20[i]:
                    sell, reason = True, '死叉'
            if sell:
                cash += shares * p; shares = 0.0
                trades.append((p / entry_px - 1) * 100)
                entry_px = None; days_flat = 0
        else:
            days_flat += 1
            buy = False
            if buy_mode == 'T' or buy_mode == 'W' and False:
                pass
            cnorm = chip / s
            if buy_mode == 'P':
                trap = cnorm[bins > p].sum() * 100
                bot5 = cnorm[(bins >= p*.95) & (bins <= p*1.05)].sum() * 100
                buy = trap >= 85 and 5 <= bot5 <= 15
            elif buy_mode == 'W':
                trap = cnorm[bins > p].sum() * 100
                buy = trap >= 60
            elif buy_mode == 'D':
                if not np.isnan(lo250[i]) and lo250[i] > 0:
                    buy = (p / lo250[i] - 1) * 100 <= 5
            if buy:
                shares = cash / p; cash = 0.0; entry_px = p; entry_d = d
                days_flat = 0
    if shares > 1e-9 and n > 0:
        trades.append((ca[-1] / entry_px - 1) * 100)
    rets = np.array(trades) if trades else np.array([])
    nav = float(np.prod(1 + rets / 100)) if len(rets) else 1.0
    return nav, len(rets), (rets > 0).mean() * 100 if len(rets) else 0


def main():
    from core.data_loader.freestockdb import fetch_daily_qfq_single
    codes = {"中兴000063": "000063", "烽火600498": "600498", "英维克002837": "002837"}
    buys = {'P恐慌': 'P', 'W宽松': 'W', 'D深跌': 'D'}
    sells = {'A波段': 'A', 'B拿住': 'B', 'C死叉走': 'C'}
    for nm, code in codes.items():
        df = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
        print(f"\n===== {nm} =====")
        hdr = "买\\卖 | " + " | ".join(f"{s:<6}" for s in sells)
        print(hdr)
        all_nav = {}
        for bl, bm in buys.items():
            row = f"{bl:<5} | "
            for sl, sm in sells.items():
                nav, nn, wr = simulate(df, bm, sm)
                all_nav[(bm, sm)] = (nav, nn, wr)
                row += f"{nav:5.2f}({nn:2d}) "
            print(row)
        # 主效应: 卖法固定取均值 vs 买点固定取均值 (几何)
        def gmean(vals):
            return float(np.exp(np.mean(np.log(np.clip(np.array(vals, dtype=float), 1e-9, None)))))
        sell_means = {sl: gmean([all_nav[(bm, sm)][0] for bm in buys.values()])
                      for sl, sm in sells.items()}
        buy_means = {bl: gmean([all_nav[(bm, sl)][0] for sl in sells.values()])
                     for bl, bm in buys.items()}
        print("  卖法均值(A/B/C): " + " ".join(f"{sl}={sell_means[sl]:.2f}" for sl in sells))
        print("  买点均值(P/W/D): " + " ".join(f"{bl}={buy_means[bl]:.2f}" for bl in buys))


if __name__ == "__main__":
    main()
