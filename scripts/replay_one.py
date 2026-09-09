# -*- coding: utf-8 -*-
"""单票回放: 纯筹码买点(n=3) + 峰顶跟踪卖, 逐笔明细 (2026-09-06)"""
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import numpy as np
from core.data_loader.freestockdb import fetch_daily_qfq_single

def replay(code, w0, w1, capital=500000.0, n_coef=3.0, pos_max=100.0):
    df = fetch_daily_qfq_single(code, "2021-01-01", "2026-09-05")
    if df is None:
        return
    ca = df["close"].values; la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values; dates = [str(d.date()).replace("-", "") for d in df.index]
    N = len(df)
    hi_max = float(ha.max()); w = max(hi_max*0.001, 0.01)
    nb = int(hi_max*1.05/w)+1; bins = np.arange(nb)*w
    chip = np.zeros(nb)
    cash, shares, entry, entry_d = capital, 0.0, None, None
    hold_hi, hhd = 0.0, 0
    vol = df["volume"].values if "volume" in df.columns else None
    trades = []
    buy_vol_day = 0.0  # 当日总成交量(股) 记录买卖
    last_buy_idx = -1
    for i in range(N):
        t = tv[i]
        if t > 0 and ha[i] > 0:
            alpha = min(t/100.0*n_coef, 1.0)
            chip *= (1-alpha)
            m = (bins >= la[i]-1e-9) & (bins <= ha[i]+1e-9)
            if m.any(): chip[m] += alpha/m.sum()
        s = chip.sum()
        if s <= 0: continue
        c = chip/s; p = ca[i]; d = dates[i]
        if not (w0 <= d <= w1): continue
        if shares > 0:
            if p > hold_hi: hold_hi = p; hhd = 0
            else: hhd += 1
            pnl = p/entry - 1
            sell, reason = False, ''
            if pnl <= -0.12: sell, reason = True, '防崩-12'
            elif pnl >= 0.30:
                if hhd >= 15: sell, reason = True, '高位滞涨15日'
                elif p < hold_hi*0.98 and hhd >= 5: sell, reason = True, '峰顶回落'
            if sell:
                sell_sh = shares
                cash += shares*p
                day_vol = (vol[i] if vol is not None and vol[i] else 0)/100.0  # 手
                trades.append((entry_d, entry, d, p, reason, pnl*100,
                               last_buy_idx, sell_sh, day_vol))
                shares = 0.0; entry=None; hold_hi=0; hhd=0
        else:
            trap = c[bins > p].sum()*100
            bot5 = c[(bins >= p*.95)&(bins <= p*1.05)].sum()*100
            if trap >= 60 and 5 <= bot5 <= 20:
                # 位置过滤: 价须在前120日区间低位(<=pos_max%)
                if pos_max < 100 and i >= 120:
                    w120 = ca[i-120:i]
                    lo, hi = w120.min(), w120.max()
                    pos = (p-lo)/(hi-lo)*100 if hi > lo else 50.0
                    if pos > pos_max:
                        continue
                shares = cash/p; cash = 0.0; entry = p; entry_d = d
                hold_hi = p; hhd = 0
                last_buy_idx = i
    if shares > 1e-9 and N > 0:
        cash += shares*ca[-1]
    return cash, trades

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="688234")
    ap.add_argument("--start", default="2024-09-04")
    ap.add_argument("--end", default="2026-09-04")
    ap.add_argument("--pos-max", type=float, default=100.0, help="位置过滤: 买入价须在前120日区间<=此%")
    a = ap.parse_args()
    cap = 500000.0
    nav, trades = replay(a.code, a.start.replace("-",""), a.end.replace("-",""), capital=cap, pos_max=a.pos_max)
    pf = f"位置≤{a.pos_max:.0f}%" if a.pos_max < 100 else "无位置过滤"
    print(f"{a.code} {a.start}~{a.end} | {pf} | 本金 {cap:,.0f} 期末 {(nav/cap-1)*100:+.1f}%\n")
    print(f"{'买日':<10}{'买价':>8}{'买量(股)':>10}{'卖日':<10}{'卖价':>8}{'卖量(股)':>10}  {'原因':<12}{'收益':>8}")
    for t in trades:
        # t = (entry_d, entry, d, p, reason, pnl, buy_idx, sell_sh, dayvol)
        buy_sh = (cap / t[1]) if t[1] else 0
        print(f"{t[0]:<10}{t[1]:>8.2f}{buy_sh:>9.0f}{t[2]:<10}{t[3]:>8.2f}{t[7]:>9.0f}  {t[4]:<12}{t[5]:>+7.1f}%")
    if not trades:
        print("无交易")

if __name__ == "__main__":
    main()
