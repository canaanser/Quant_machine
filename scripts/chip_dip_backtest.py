# -*- coding: utf-8 -*-
"""筹码抄底策略实验（2026-09-06 老板测试机，可随时还原）

规则：
  触发条件（每日 T，只用 ≤T 数据，无未来函数）:
    ① 筹码套牢盘 ≥ TRAP_MIN (默认0.55)  ← 越套越深才有戏
    ② 价距250日低点 < 20% (确认在底部区)
    ③ 换手 < 近60日中位 (缩量=没人卖了=洗够了)
  仓位: 套牢越重买越多 —— weight = clip((trap - TRAP_MIN)/(0.95 - TRAP_MIN), 0, 1)
  卖出: 涨 TH 20% 止盈 或 跌破买入价 STOP 10% (简单纪律)
  ⚠️ 信号只在"空仓"时触发一次买入（不连续加仓），持到卖出信号再重新找

用法: python -B scripts/chip_dip_backtest.py --code 300502 --start 2024-01-01 --end 2026-09-03
      python -B scripts/chip_dip_backtest.py --pool 精选15 --start 2024-01-01
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import json
import urllib.request
import urllib.parse
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent))


def load_daily(code: str, y0=2018, y1=2026):
    """统一取数：Windows=SDK qfq 前复权；WSL=HTTP+折算(自检)。口径与主引擎一致。"""
    from core.data_loader.freestockdb import fetch_daily_qfq_single
    df = fetch_daily_qfq_single(code, f"{y0}-01-01", f"{y1}-12-31")
    out = {}
    for d, r in df.iterrows():
        out[d.strftime("%Y%m%d")] = {
            "open": r["open"], "high": r["high"], "low": r["low"],
            "close": r["close"], "volume": r["volume"], "turnover": r["turnover"],
        }
    return out


def chip_at(daily: dict, date: str, lookback=400, step=0.5):
    """筹码分布（只用<=date）。返回 (bins, chip)"""
    import numpy as np
    dates = sorted(d for d in daily if d <= date)[-lookback:]
    if not dates:
        return None, None
    closes = [float(daily[d]["close"]) for d in dates]
    lo_all, hi_all = min(closes), max(closes)
    bins = np.arange(max(0.5, lo_all - step * 20), hi_all + step * 20, step)
    chip = np.zeros(len(bins))
    for d in dates:
        r = daily[d]
        lo, hi = float(r["low"]), float(r["high"])
        tv = float(r["turnover"]) / 100
        chip = chip * (1 - tv)
        m = (bins >= lo) & (bins < hi)
        if m.any():
            chip[m] += tv / m.sum()
    s = chip.sum()
    return (bins, chip / s) if s > 0 else (bins, chip)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default=None)
    ap.add_argument("--pool", default=None, help="84/精选15/研究方向(在 config 里)")
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-09-03")
    ap.add_argument("--trap-min", type=float, default=0.55)
    ap.add_argument("--trap-cap", type=float, default=1.00,
                    help="套牢上限(可关: 1.0=不限)")
    ap.add_argument("--bot5-min", type=float, default=0.0,
                    help="底部筹码占比下限(0.30=30%, 0.0=关闭)")
    ap.add_argument("--mode", default="classic", choices=["classic", "chip2"],
                    help="classic=旧规则(套牢+距低点+换手缩量) chip2=纯筹码两维(套牢+底部筹码)")
    ap.add_argument("--take-profit", type=float, default=0.20)
    ap.add_argument("--stop-loss", type=float, default=0.10)
    args = ap.parse_args()
    import numpy as np

    if args.code:
        codes = [args.code]
    elif args.pool:
        from config.config import SCAN_TICKERS_CURATED, SCAN_TICKERS
        codes = list(SCAN_TICKERS_CURATED) if args.pool == "精选15" else list(SCAN_TICKERS)
        if len(codes) > 6:
            codes = codes[:6]  # 测试机先跑前几只
    else:
        print("需 --code 或 --pool"); return

    TRAP_MIN, TRAP_CAP, BOT5_MIN, TP, SL = (args.trap_min, args.trap_cap,
                                          args.bot5_min, args.take_profit, args.stop_loss)
    s0, e0 = args.start.replace("-", ""), args.end.replace("-", "")
    print(f"筹码抄底实验 | 套牢[{TRAP_MIN:.0%},{TRAP_CAP:.0%}] 底部筹码≥{BOT5_MIN:.0%} "
          f"止盈+{TP:.0%} 止损-{SL:.0%} | {args.start}~{args.end}")
    print("=" * 60)

    for code in codes:
        daily = load_daily(code)
        dates = sorted(d for d in daily if s0 <= d <= e0)
        if not dates:
            continue
        # 状态机
        cash = 1.0; shares = 0.0; entry_px = None; equity = []
        trades = 0
        buy_dates = []
        for d in dates:
            r = daily[d]
            px = float(r["close"])
            if shares > 0:
                # 持仓中：检查卖出
                if px >= entry_px * (1 + TP) or px <= entry_px * (1 - SL):
                    cash += shares * px
                    shares = 0.0; entry_px = None; trades += 1
            else:
                # 空仓：检查筹码抄底信号
                bins, chip = chip_at(daily, d)
                if chip is None or chip.sum() == 0:
                    continue
                trap = chip[bins > px].sum() / chip.sum() if chip.sum() > 0 else 0
                # 距250日低点
                win = sorted(d for d in daily if d <= d)[-250:]
                lo250 = min(float(daily[x]["close"]) for x in win) if win else px
                dd = (px / lo250 - 1)
                tv_now = float(r["turnover"])
                tv_hist = [float(daily[x]["turnover"]) for x in win[-60:]] if len(win) >= 60 else [tv_now]
                vol_shrink = tv_now <= float(np.median(tv_hist))
                bot5 = chip[(bins >= px * .95) & (bins <= px * 1.05)].sum() / chip.sum() \
                    if chip.sum() > 0 else 0.0
                if args.mode == "chip2":
                    # 纯筹码两维：套牢下限 + 底部筹码下限（老板：换手率是随机玩意，不加）
                    sig = (TRAP_MIN <= trap <= TRAP_CAP and bot5 >= BOT5_MIN)
                else:
                    # classic 旧规则：套牢 + 距低点 + 换手缩量
                    win = sorted(d for d in daily if d <= d)[-250:]
                    lo250 = min(float(daily[x]["close"]) for x in win) if win else px
                    dd = (px / lo250 - 1)
                    tv_now = float(r["turnover"])
                    tv_hist = [float(daily[x]["turnover"]) for x in win[-60:]] if len(win) >= 60 else [tv_now]
                    vol_shrink = tv_now <= float(np.median(tv_hist))
                    sig = (TRAP_MIN <= trap <= TRAP_CAP and bot5 >= BOT5_MIN
                           and dd < 0.20 and vol_shrink)
                if sig:
                    # 仓位 = (trap-TRAP_MIN)/(0.95-TRAP_MIN)
                    w = min(1.0, max(0.0, (trap - TRAP_MIN) / (0.95 - TRAP_MIN)))
                    buy_amt = cash * w
                    shares = buy_amt / px
                    cash -= buy_amt
                    entry_px = px
                    buy_dates.append((d, px, trap * 100, bot5 * 100))
            equity.append(cash + shares * px)
        # 期末
        final = equity[-1] if equity else 1.0
        n_buy = len(buy_dates)
        print(f"{code}: 期末净值 {final:.2f} ({(final-1)*100:+.0f}%) | 买入{n_buy}次 平仓{trades}次")
        if buy_dates[:3]:
            for b in buy_dates[:3]:
                print(f"    买: {b[0]} @{b[1]:.2f} 套牢{b[2]:.0f}% 底部筹码{b[3]:.0f}%")


if __name__ == "__main__":
    main()
