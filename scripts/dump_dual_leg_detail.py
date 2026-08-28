# -*- coding: utf-8 -*-
"""
DualLeg 双腿回测——指定年份交易明细（解释 2018 熊市 +171% 之谜）
=====================================================================
2026-08-28 小二陈：分年表显示 DualLeg 在 2018（+171.4%）、2023（+32.3%）
等弱市年大幅跑赢 Simple，需看该年交易明细，确认收益来源（哪些票/哪个月）。

用法（Windows，需 stockdb.exe 服务）：
    cd E:/stockgate/Quant_Alpha_System
    python scripts/dump_dual_leg_detail.py            # 默认 2018
    python scripts/dump_dual_leg_detail.py --year 2023
    python scripts/dump_dual_leg_detail.py --year 2024 --monthly  # 只看每月
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import DualLegStrategy
import config.config as config_mod

START, END = '2017-01-01', '2026-08-27'
INITIAL_CASH = 500000
DEFAULT_TICKERS = list(config_mod.SCAN_TICKERS)


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description="DualLeg 指定年份交易明细")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    parser.add_argument("--year", type=int, default=2018)
    parser.add_argument("--monthly", action="store_true", help="只打印该年月收益")
    args = parser.parse_args()

    names = {}
    p = PROJECT_ROOT / 'data' / 'stock_names.json'
    if p.exists():
        names = json.loads(p.read_text(encoding='utf-8'))

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    print(f"🚀 回测中：{len(tickers)} 只，{args.start} ~ {args.end} ...")
    market_data = load_data(
        source='freestockdb', tickers=tickers,
        start=args.start, end=args.end, frequency='1d', fq='qfq'
    )
    t0 = time.time()
    eng = BacktestPipeline(DualLegStrategy(5, 20), top_n=10, verbose=False)
    eng.run(market_data, initial_cash=INITIAL_CASH, auto_save=False)
    print(f"✅ 回测完成：累计 {eng.total_return:.2%}，耗时 {time.time()-t0:.1f}s")

    # 该年月度收益
    eq = eng.equity_curve
    y = args.year
    seg = eq[eq.index.year == y]
    if len(seg) < 2:
        print(f"⚠️ {y} 年无数据")
        return
    year_ret = seg.iloc[-1] / seg.iloc[0] - 1
    print(f"\n===== {y} 年账户收益：{year_ret:.2%} =====")
    if args.monthly or True:
        months = sorted(set(seg.index.month))
        prev = seg.iloc[0]
        for m in months:
            ms = seg[seg.index.month == m]
            if len(ms) > 1:
                mr = ms.iloc[-1] / prev - 1
                print(f"  {y}-{m:02d}: {mr:+.2%}")
                prev = ms.iloc[-1]

    # 该年交易明细
    df = eng.trades.copy()
    df['Date'] = df['Date'].astype(str).str[:10]
    yd = df[df['Date'].str.startswith(str(y))]
    print(f"\n{y} 年交易：{len(yd)} 笔（买 {len(yd[yd['Action']=='BUY'])} / 卖 {len(yd[yd['Action']=='SELL'])}）")

    if args.monthly:
        return

    # 每只股票该年实现盈亏（加权平均成本）
    from collections import defaultdict
    state = defaultdict(lambda: {'shares': 0, 'avg': 0.0, 'pnl': 0.0})
    for _, r in yd.iterrows():
        st = state[r['Stock']]
        if r['Action'] == 'BUY':
            tot = st['shares'] + r['Shares']
            st['avg'] = (st['avg'] * st['shares'] + r['Price'] * r['Shares']) / tot if tot else r['Price']
            st['shares'] = tot
        else:
            st['pnl'] += (r['Price'] - st['avg']) * r['Shares']
            st['shares'] -= r['Shares']
    rows = sorted(((st['pnl'], code) for code, st in state.items()), reverse=True)
    print(f"\n===== {y} 年实现盈亏 Top 12（含未平仓）=====")
    for pnl, code in rows[:12]:
        st = state[code]
        flag = '（持仓中）' if st['shares'] > 0 else ''
        print(f"  {code} {names.get(code,'?'):<8} {pnl:>+12,.0f} 元  {st['shares']:>6}股{flag}")
    print(f"\n===== {y} 年实现亏损 Bottom 8 =====")
    for pnl, code in rows[-8:]:
        st = state[code]
        print(f"  {code} {names.get(code,'?'):<8} {pnl:>+12,.0f} 元  {st['shares']:>6}股")

    # 该年每月 持仓 Top（每月末前5持仓）
    print(f"\n===== {y} 年每月末 Top5 持仓（市值）=====")
    holdings = defaultdict(float)  # code -> shares
    prices = {}
    for _, r in yd.iterrows():
        holdings[r['Stock']] += r['Shares'] if r['Action'] == 'BUY' else -r['Shares']
    # 按月末时点近似：直接看期末持仓
    for code, sh in sorted(holdings.items(), key=lambda kv: -kv[1])[:10]:
        if sh > 0:
            print(f"  {code} {names.get(code,'?'):<8} {sh:>8}股")


if __name__ == "__main__":
    main()
