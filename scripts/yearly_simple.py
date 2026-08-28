# -*- coding: utf-8 -*-
"""
Simple（抄底单腿）分年收益表——验证修复后 567.93% 的年度结构
=====================================================================
2026-08-28 小二陈：风控修复（单票上限 20%）后 Simple 84 只 10 年 567.93% /
Sharpe 0.51 / 回撤 -32.42%，需逐年拆分确认年度稳健性（非单年暴击）。

用法（Windows，需 stockdb.exe 服务）：
    cd E:/stockgate/Quant_Alpha_System
    python scripts/yearly_simple.py
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy
import config.config as config_mod

START, END = '2017-01-01', '2026-08-27'
INITIAL_CASH = 500000
DEFAULT_TICKERS = list(config_mod.SCAN_TICKERS)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Simple 单腿分年收益表")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    print(f"🚀 回测中：{len(tickers)} 只，{args.start} ~ {args.end} ...")
    market_data = load_data(
        source='freestockdb', tickers=tickers,
        start=args.start, end=args.end, frequency='1d', fq='qfq'
    )
    t0 = time.time()
    eng = BacktestPipeline(SimpleStrategy(5, 20), top_n=10, verbose=False)
    eng.run(market_data, initial_cash=INITIAL_CASH, auto_save=False)
    print(f"✅ 回测完成：累计 {eng.total_return:.2%}，耗时 {time.time()-t0:.1f}s")

    eq = eng.equity_curve
    trades = eng.trades
    trades['Date'] = trades['Date'].astype(str).str[:10]

    years = sorted(set(eq.index.year))
    print("\n" + "=" * 64)
    print(f"{'年份':<8}{'当年收益':>10}{'年末资产':>14}{'当年交易':>10}{'正月份':>8}")
    print("-" * 64)
    prev = eq.iloc[0]
    good_years = 0
    for y in years:
        seg = eq[eq.index.year == y]
        if len(seg) < 2:
            continue
        yr = seg.iloc[-1] / prev - 1
        yt = trades[trades['Date'].str.startswith(str(y))]
        # 正月份统计
        months = sorted(set(seg.index.month))
        pv = prev
        pos_months = 0
        for m in months:
            ms = seg[seg.index.month == m]
            if len(ms) > 1:
                if ms.iloc[-1] / pv - 1 > 0:
                    pos_months += 1
                pv = ms.iloc[-1]
        mark = " ✅" if yr > 0 else " ❌"
        if yr > 0:
            good_years += 1
        print(f"{y:<8}{yr:>9.2%}{seg.iloc[-1]:>14,.0f}{len(yt):>10d}{pos_months:>6d}/12{mark}")
        prev = seg.iloc[-1]
    print("-" * 64)
    print(f"{'累计':<8}{eng.total_return:>9.2%}")
    print(f"年化 {eng.annual_return:.2%} | Sharpe {eng.sharpe:.2f} | 最大回撤 {eng.max_drawdown:.2%} | "
          f"总交易 {len(trades)} | 正收益年 {good_years}/{len(years)}")
    print("=" * 64)


if __name__ == "__main__":
    main()
