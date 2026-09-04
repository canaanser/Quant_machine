# -*- coding: utf-8 -*-
"""
162 只扩池回撤诊断：最大回撤窗口 + 窗口期交易 + 分年回撤
=====================================================================
2026-08-28 小二陈：扩池 162 只原版回撤 -73.74%（84 只仅 -32%），
诊断回撤集中在哪个时段、策略在窗口期抄底了哪些票（揪出元凶）。

用法（Windows，需 stockdb.exe 服务，python -B 防缓存）：
    cd E:/stockgate/Quant_Alpha_System
    python -B scripts/diagnose_drawdown.py --ext
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import numpy as np
import pandas as pd

from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy
import config.config as config_mod

START, END = '2017-01-01', '2026-08-27'
INITIAL_CASH = 500000


def load_names():
    p = PROJECT_ROOT / 'data' / 'stock_names.json'
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return {}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="162 只扩池回撤诊断")
    parser.add_argument("--ext", action="store_true", help="合并池 162 只")
    parser.add_argument("--tickers", default=",".join(config_mod.SCAN_TICKERS))
    parser.add_argument("--no-quality", action="store_true", help="原版（默认）")
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    args = parser.parse_args()

    if args.ext:
        tickers = list(config_mod.SCAN_TICKERS) + list(config_mod.SCAN_TICKERS_EXT)
        print(f"📦 合并池 {len(tickers)} 只")
    else:
        tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]

    print(f"🚀 回测中：{len(tickers)} 只 ...")
    md = load_data(source='freestockdb', tickers=tickers,
                   start=args.start, end=args.end, frequency='1d', fq='qfq')
    strategy = SimpleStrategy(5, 20, quality_filter=not args.no_quality, quality_penalty=0.1)
    eng = BacktestPipeline(strategy, top_n=10, verbose=False)
    eng.run(md, initial_cash=INITIAL_CASH, auto_save=False)
    print(f"✅ 累计 {eng.total_return:.2%} 回撤 {eng.max_drawdown:.2%} 交易 {len(eng.trades)}")

    eq = eng.equity_curve
    dd = eq / eq.cummax() - 1
    trough_idx = dd.idxmin()
    trough = dd.min()
    # 回撤窗口起点：trough 前最近的高点
    peak_idx = eq[:trough_idx].idxmax()
    # 恢复点：trough 后首次回到 peak 水平
    rec = eq[trough_idx:][eq[trough_idx:] >= eq[peak_idx]]
    rec_idx = rec.index[0] if len(rec) else eq.index[-1]
    print(f"\n===== 最大回撤窗口 =====")
    print(f"  高点 {peak_idx.date()} ({eq[peak_idx]:,.0f}) → 谷底 {trough_idx.date()} ({eq[trough_idx]:,.0f}, {trough:.2%})")
    print(f"  恢复 {rec_idx.date()}（或未恢复至 {eq.index[-1].date()}）")

    # 窗口期交易
    trades = eng.trades.copy()
    trades['Date'] = trades['Date'].astype(str).str[:10]
    w0, w1 = str(peak_idx.date()), str(trough_idx.date())
    wt = trades[(trades['Date'] >= w0) & (trades['Date'] <= w1)]
    names = load_names()
    print(f"\n===== 窗口期交易（{w0} ~ {w1}，{len(wt)} 笔）=====")
    if len(wt):
        # 按票聚合：买入金额/卖出金额/笔数
        buys = wt[wt['Action'] == 'BUY']
        sells = wt[wt['Action'] == 'SELL']
        agg = {}
        for _, r in buys.iterrows():
            a = agg.setdefault(r['Stock'], {'buy': 0.0, 'sell': 0.0, 'nb': 0, 'ns': 0})
            a['buy'] += r['Price'] * r['Shares']
            a['nb'] += 1
        for _, r in sells.iterrows():
            a = agg.setdefault(r['Stock'], {'buy': 0.0, 'sell': 0.0, 'nb': 0, 'ns': 0})
            a['sell'] += r['Price'] * r['Shares']
            a['ns'] += 1
        # 窗口期价格跌幅
        print(f"{'代码':<8}{'名称':<10}{'买入额':>12}{'笔数':>6}{'窗口跌幅':>10}")
        for code, a in sorted(agg.items(), key=lambda kv: -kv[1]['buy'])[:15]:
            if code in md.price.columns:
                pcol = md.price[code].dropna()
                p0 = pcol.asof(w0) if hasattr(pcol, 'asof') else np.nan
                p1 = pcol.asof(w1)
                chg = p1 / p0 - 1 if p0 and p1 and p0 > 0 else np.nan
            else:
                chg = np.nan
            print(f"{code:<8}{names.get(code, '?'):<10}{a['buy']:>12,.0f}{a['nb']:>6d}{chg:>9.1%}")

    # 分年最大回撤
    print(f"\n===== 分年最大回撤 =====")
    for y in sorted(set(eq.index.year)):
        seg = eq[eq.index.year == y]
        if len(seg) > 60:
            sdd = (seg / seg.cummax() - 1).min()
            print(f"  {y}: {sdd:.2%}")
    print(f"\n窗口期买入 Top 票 = 回撤元凶候选（若窗口跌幅大且买入多）")


if __name__ == "__main__":
    main()
