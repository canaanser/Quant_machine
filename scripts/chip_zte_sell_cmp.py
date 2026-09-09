# -*- coding: utf-8 -*-
r"""中兴 000063：筹码恐慌区买点 × 两套卖法对比（2026-09-06 老板：卖法决定收益）

买点（筹码两维，老板恐慌区口径）：
  ① 套牢盘 ≥ trap_floor（可调，如 0.85）
  ② 底部筹码 5%≤bot5≤15%（洗干净的恐慌区；实证最优格 5-10%）
仓位：单票全仓1.0（先比买卖规则，不比仓位）

卖法 A（糙，扫描器现状）：先触 +TP(0.20) 止盈 / −SL(0.10) 止损 / 60日末平
卖法 B（主引擎成熟纪律，core/risk_manager.py 复刻）：
  ① 止损=认错：跌破 avg_cost×(1−sl_base)；浮盈>0 时止损线下移放宽(回吐到成本×(1−sl_base)才卖)
  ② 止盈=锁利卖半：浮盈≥tp(默认2×sl) 卖一半；剩半仓继续
  ③ 死叉卖出(MA5下穿MA20)真假判定：
     - 浮盈>0 → 不卖（交止盈/动态止损管）
     - 底背离（价新低RSI未新低）→ 不卖
     - 低位死叉（价距250日高< −40%）→ 不卖（深跌区不割）
     - 真死叉 → 清仓
输出每笔(买日/买价/卖日/卖价/持有天数/原因/收益) + 汇总

用法（Windows）：python -B scripts/chip_zte_sell_cmp.py [--trap 0.85]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

TP, SL, HZ = 0.20, 0.10, 60
SL_BASE = 0.10        # 止损认错线（A/B 共用底线口径）
DEADCROSS_LOW = -0.40  # 低位死叉阈值


def rsi14(closes):
    n = len(closes)
    out = np.full(n, np.nan)
    if n < 15:
        return out
    d = np.diff(closes)
    for i in range(14, n):
        up = d[i-14:i]
        gain = up[up > 0].sum() / 14
        loss = -up[up < 0].sum() / 14
        out[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss) if loss > 0 else 100.0
    return out


START = "20240101"


def run_one(df, trap_floor, mode):
    """mode: 'A糙' or 'B成熟'。返回 (trades, final_nav)"""
    import pandas as pd
    n = len(df)
    d0, d1 = START, "20260903"
    ca = df["close"].values
    dates = [d.strftime("%Y%m%d") for d in df.index]
    la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    # MA
    c = pd.Series(ca)
    ma5 = c.rolling(5).mean().values
    ma20 = c.rolling(20).mean().values
    # RSI14(用窗口内的日收益近似; 完整用close diff)
    rsi = rsi14(ca)
    hi250 = c.rolling(250).max().values

    # 筹码游走
    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)

    trades = []
    cash, shares, entry_px, entry_d, half_done = 1.0, 0.0, None, None, False
    nav_hist = []
    trades_open_cost = None
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
        if not (d0 <= d <= d1):
            continue
        if shares > 0:
            pnl = p / entry_px - 1
            sold = 0.0
            reason = None
            if mode == 'C死叉即走':
                # 死叉(MA5下穿MA20)一律清仓；止损线同B(成本-10%,浮盈放宽底线);无止盈锁半
                if p <= entry_px * (1 - SL_BASE):
                    sold = shares; reason = '止损认错'
                elif i > 1 and not np.isnan(ma5[i]) and not np.isnan(ma20[i]) \
                        and ma5[i - 1] >= ma20[i - 1] and ma5[i] < ma20[i]:
                    sold = shares; reason = '死叉清仓'
            elif mode == 'A糙':
                if p >= entry_px * (1 + TP):
                    sold = shares; reason = '止盈+20%'
                elif p <= entry_px * (1 - SL):
                    sold = shares; reason = '止损-10%'
            else:
                # ①止损=认错（浮盈放宽：回吐到成本线才卖，不保本保垫子）
                sl_line = entry_px * (1 - SL_BASE)
                if pnl > 0:
                    # 浮盈越厚止损线下移越多，最多成本×1.25档——但永远≥机械底线
                    stretch = SL_BASE * (1 + min(pnl, 0.25))
                    sl_line = max(entry_px * (1 - stretch), entry_px * (1 - SL_BASE))
                if p <= sl_line:
                    sold = shares; reason = '止损认错'
                # ②止盈锁利卖半（浮盈≥2×sl=20% 且 未卖过半）
                elif not half_done and pnl >= 2 * SL_BASE:
                    half = shares / 2
                    sold = half; reason = '止盈锁半'
                    half_done = True
                # ③死叉真假判定
                if sold == 0 and i > 1 and not np.isnan(ma5[i]) and not np.isnan(ma20[i]) \
                        and ma5[i - 1] >= ma20[i - 1] and ma5[i] < ma20[i]:
                    # 浮盈 → 不卖
                    if pnl > 0:
                        reason = None
                    elif rsi is not None and not np.isnan(rsi[i]) and not np.isnan(rsi[i - 1]):
                        # 底背离：价新低但 RSI 未新低 → 不卖
                        px_lo = ca[max(0, i - 14):i + 1].min()
                        prev_lo = ca[max(0, i - 28):i - 13].min() if i > 27 else px_lo
                        rsi_lo = np.nanmin(rsi[max(0, i - 14):i + 1])
                        prev_rsi_lo = np.nanmin(rsi[max(0, i - 28):i - 13]) if i > 27 else rsi_lo
                        if p <= px_lo and prev_lo < px_lo and rsi_lo < prev_rsi_lo:
                            reason = None
                        elif hi250[i] is not None and not np.isnan(hi250[i]) \
                                and (p / hi250[i] - 1) < DEADCROSS_LOW:
                            reason = None  # 低位死叉不割
                        else:
                            sold = shares; reason = '真死叉清仓'
                    else:
                        if hi250[i] is not None and not np.isnan(hi250[i]) \
                                and (p / hi250[i] - 1) < DEADCROSS_LOW:
                            reason = None
                        else:
                            sold = shares; reason = '真死叉清仓'
                if sold == 0 and reason is not None and '止盈锁半' in reason:
                    pass  # half handled above
            if sold > 0:
                cash += sold * p
                shares -= sold
                if shares <= 1e-9:
                    ret = (p / entry_px - 1) * 100
                    trades.append((entry_d, round(entry_px, 2), d, round(p, 2),
                                   (len([x for x in dates if entry_d <= x <= d])), reason, round(ret, 1)))
                    entry_px = None; half_done = False
                elif sold < 1e-9 and False:
                    pass
        else:
            cnorm = chip / s
            trap = cnorm[bins > p].sum() * 100
            bot5 = cnorm[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if trap >= trap_floor * 100 and 5 <= bot5 <= 15:
                buy_amt = cash
                shares = buy_amt / p
                cash = 0.0
                entry_px = p
                entry_d = d
                half_done = False
        nav_hist.append(cash + shares * p)
    # 持仓跨期末按最后价结
    if shares > 1e-9 and n > 0:
        p = ca[-1]
        ret = (p / entry_px - 1) * 100
        trades.append((entry_d, round(entry_px, 2), dates[-1], round(p, 2),
                       len([x for x in dates if entry_d <= x <= dates[-1]]), '期末持仓', round(ret, 1)))
        cash += shares * p
    return trades, nav_hist[-1] if nav_hist else 1.0


def main():
    import argparse
    from core.data_loader.freestockdb import fetch_daily_qfq_single
    ap = argparse.ArgumentParser()
    ap.add_argument("--trap", type=float, default=0.85)
    ap.add_argument("--code", default="000063")
    ap.add_argument("--start", default="2024-01-01")
    args = ap.parse_args()
    global START
    START = args.start.replace("-", "")
    y0 = max(2019, int(args.start[:4]) - 3)
    df = fetch_daily_qfq_single(args.code, f"{y0}-01-01", "2026-12-31")
    if df is None or len(df) < 300:
        print("无数据"); return
    print(f"{args.code} 筹码恐慌买点(套牢≥{args.trap:.0%},底部5-15%) × 卖法对比 | {args.start}~2026-09\n")
    for mode in ['A糙', 'B成熟', 'C死叉即走']:
        trades, nav = run_one(df, args.trap, mode)
        rets = np.array([t[6] for t in trades])
        wins = (rets > 0).sum()
        print(f"[卖法 {mode}] 期末净值 {nav:.2f} ({(nav-1)*100:+.0f}%) | 平仓 {len(trades)}笔 "
              f"胜率 {wins/max(len(trades),1)*100:.0f}% 均收 {rets.mean():+.1f}% 中位 {np.median(rets):+.1f}%")
        for t in trades[:12]:
            print(f"   买{t[0]}@{t[1]:.2f} → 卖{t[2]}@{t[3]:.2f} 持{t[4]}日 {t[5]} 收{t[6]:+.1f}%")
        if len(trades) > 12:
            print(f"    ... 其余{len(trades)-12}笔")
        print()


if __name__ == "__main__":
    main()
