# -*- coding: utf-8 -*-
r"""验证：买点择时是不是结果的关键（老板 2026-09-06）
三只票 × 同一卖法(死叉即走) × 三种买点：
  P恐慌筹码: trap>=85% 且 5%<=bot5<=15%      (现状买点)
  T时间:     每60交易日空仓就买(不看任何信号)
  D深跌:     价距250日低点<=5%(深跌低位,不看筹码)
同卖法下比收益差 → 若 P 显著赢 T/D, 证明"什么时候买"是关键
2024-01-01 ~ 2026-09-03
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import numpy as np
import pandas as pd

START = "20240101"
TP, SL, HZ = 0.20, 0.10, 60
SL_BASE = 0.10


def simulate(df, buy_mode):
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
    days_since_flat = 0
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
            if p <= entry_px * (1 - SL_BASE):
                cash += shares * p; shares = 0.0
                trades.append((entry_d, entry_px, d, p, '止损', (p/entry_px-1)*100))
                entry_px = None; days_since_flat = 0
            elif i > 1 and not np.isnan(ma5[i]) and not np.isnan(ma20[i]) \
                    and ma5[i-1] >= ma20[i-1] and ma5[i] < ma20[i]:
                cash += shares * p; shares = 0.0
                trades.append((entry_d, entry_px, d, p, '死叉', (p/entry_px-1)*100))
                entry_px = None; days_since_flat = 0
        else:
            days_since_flat += 1
            buy = False
            if buy_mode == 'T':
                buy = days_since_flat >= 60   # 纯时间：每60交易日买
            else:
                cnorm = chip / s
                if buy_mode == 'P':
                    trap = cnorm[bins > p].sum() * 100
                    bot5 = cnorm[(bins >= p*.95) & (bins <= p*1.05)].sum() * 100
                    buy = trap >= 85 and 5 <= bot5 <= 15
                elif buy_mode == 'W':
                    trap = cnorm[bins > p].sum() * 100
                    buy = trap >= 60  # 宽松：套牢>60全信号(含半山腰)
                elif buy_mode == 'D':
                    if not np.isnan(lo250[i]) and lo250[i] > 0:
                        dd = (p / lo250[i] - 1) * 100
                        buy = dd <= 5  # 贴近250日低点
            if buy:
                shares = cash / p; cash = 0.0; entry_px = p; entry_d = d
                days_since_flat = 0
    if shares > 1e-9 and n > 0:
        p = ca[-1]
        trades.append((entry_d, entry_px, dates[-1], p, '期末', (p/entry_px-1)*100))
    return trades


def main():
    from core.data_loader.freestockdb import fetch_daily_qfq_single
    codes = {"中兴": "000063", "烽火": "600498", "英维克": "002837"}
    print(f"{'票':<6}{'买点':<6}{'总收益':>9}{'年化':>9}{'笔数':>6}{'胜率':>7}  平均每笔")
    for nm, code in codes.items():
        df = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
        for mode, label in [('P', '恐慌筹码'), ('W', '宽松套牢60'), ('D', '深跌低位')]:
            trades = simulate(df, mode)
            if not trades:
                print(f"{nm:<6}{label:<6} 无交易")
                continue
            rets = np.array([t[5] for t in trades])
            nav = np.prod(1 + rets / 100)
            years = 2.67
            ann = (nav ** (1 / years) - 1) * 100
            print(f"{nm:<6}{label:<6}{(nav-1)*100:+8.1f}%{ann:+8.1f}%{len(trades):>6}"
                  f"{(rets>0).mean()*100:>6.0f}%  {rets.mean():+.1f}%")
        print()


if __name__ == "__main__":
    main()
