# -*- coding: utf-8 -*-
"""
进攻模式 · 单票对比：中兴通讯(000063) vs 中钨高新(000657) · 近1年/近2年
=========================================================================
2026-08-30 老板：以当前策略（双均线金叉5/20+质量+位置+筑底）、进攻模式
（30%仓位+止损8%+分批），分别测近1年（2025-08-28起）和近2年（2024-08-28起）。

用法（Windows，python -B）：
    python -B scripts/compare_zte_vs_ztgx.py
"""
import copy
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy
from config.risk_config import DEFAULT_RISK_CONFIG

INITIAL_CASH = 500000
TICKERS = ['000063', '000657']
NAMES = {'000063': '中兴通讯', '000657': '中钨高新'}
END = '2026-08-28'


def run_one(ticker, start):
    strategy = SimpleStrategy(5, 20, quality_filter=True, quality_penalty=0.1, bottom_confirm=True)
    rc = copy.deepcopy(DEFAULT_RISK_CONFIG)
    rc.update({'MAX_SINGLE_POSITION_RATIO': 0.30, 'BASE_POSITION_RATIO': 0.50})
    engine = BacktestPipeline(strategy, top_n=10, risk_config=rc,
                              stop_loss_pct=0.08, batch_exit=True)
    md = load_data(source='freestockdb', tickers=[ticker],
                   start=start, end=END, frequency='1d', fq='qfq')
    engine.run(md, initial_cash=INITIAL_CASH, auto_save=False)
    return {
        '收益': f"{engine.total_return:.2%}",
        '年化': f"{engine.annual_return:.2%}",
        'Sharpe': f"{engine.sharpe:.2f}",
        '回撤': f"{engine.max_drawdown:.2%}",
        '交易': len(engine.trades),
    }


def main():
    # 近1年 = 2025-08-28 起；近2年 = 2024-08-28 起（给足 warmup）
    starts = {'近1年': '2025-08-28', '近2年': '2024-08-28'}
    results = []
    for window, start in starts.items():
        for ticker in TICKERS:
            r = run_one(ticker, start)
            r['窗口'] = window
            r['标的'] = f"{NAMES[ticker]}({ticker})"
            results.append(r)
            print(f"  {window} {NAMES[ticker]} 跑完: {r['收益']} / {r['交易']}笔")

    print("\n" + "=" * 84)
    print("进攻模式（30%仓位+止损8%+分批）· 中兴通讯 vs 中钨高新 · 近1年/近2年")
    print("=" * 84)
    print(f"{'窗口':<6}{'标的':<14}{'累计收益':>9}  {'年化':>8}  {'Sharpe':>6}  {'最大回撤':>9}  {'交易':>6}")
    print("-" * 84)
    for r in results:
        print(f"{r['窗口']:<6}{r['标的']:<14}{r['收益']:>9}  {r['年化']:>8}  {r['Sharpe']:>6}  {r['回撤']:>9}  {r['交易']:>6}")
    print("=" * 84)


if __name__ == '__main__':
    main()
