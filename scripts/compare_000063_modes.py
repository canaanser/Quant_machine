# -*- coding: utf-8 -*-
"""
000063 中兴通讯 · 最近一年 · 三模式对比（2026-08-30 小二陈）
============================================================
对比 标准 / 建仓 / 进攻 三个模式在 000063 上的表现，
重点看"近1年"（2025-08-27 ~ 2026-08-27）窗口（老板：实盘视角）。
数据从 2024-01-01 起加载（给足 250 日位置加权 + 42 日金叉 warmup）。

用法（Windows，python -B）：
    python -B scripts/compare_000063_modes.py
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
TICKER = '000063'
START, END = '2024-01-01', '2026-08-27'


def run_mode(mode: str):
    strategy = SimpleStrategy(5, 20, quality_filter=True, quality_penalty=0.1)
    rc = copy.deepcopy(DEFAULT_RISK_CONFIG)
    stop_loss = take_profit = None
    batch = protect = False
    if mode == '建仓':
        rc.update({'MAX_SINGLE_POSITION_RATIO': 0.10, 'BASE_POSITION_RATIO': 0.20})
        stop_loss, batch, protect = 0.05, True, 2
    elif mode == '进攻':
        rc.update({'MAX_SINGLE_POSITION_RATIO': 0.30, 'BASE_POSITION_RATIO': 0.50})
        stop_loss, batch = 0.08, True
    engine = BacktestPipeline(strategy, top_n=10, risk_config=rc, verbose=False,
                              stop_loss_pct=stop_loss, take_profit_pct=take_profit,
                              batch_exit=batch, protect_days=protect)
    md = load_data(source='freestockdb', tickers=[TICKER],
                   start=START, end=END, frequency='1d', fq='qfq')
    engine.run(md, initial_cash=INITIAL_CASH, auto_save=False)
    # 近1年窗口（实盘视角）
    eq = engine.equity_curve
    w0 = eq.index[-1] - pd.DateOffset(years=1)
    seg = eq[eq.index >= w0]
    yr_ret = seg.iloc[-1] / seg.iloc[0] - 1 if len(seg) > 60 else float('nan')
    yr_dd = (seg / seg.cummax() - 1).min() if len(seg) > 60 else float('nan')
    return {
        '模式': mode,
        '全区间收益': f"{engine.total_return:.2%}",
        '全区间Sharpe': f"{engine.sharpe:.2f}",
        '近1年收益': f"{yr_ret:.2%}" if yr_ret == yr_ret else "-",
        '近1年回撤': f"{yr_dd:.2%}" if yr_dd == yr_dd else "-",
        '交易数': len(engine.trades),
        '止损': f"{stop_loss:.0%}" if stop_loss else "无",
    }


def main():
    print(f"000063 中兴通讯 · {START} ~ {END}（近1年 = 2025-08-27 起）")
    results = []
    for mode in ('标准', '建仓', '进攻'):
        r = run_mode(mode)
        results.append(r)
        print(f"  {mode} 跑完: {r['全区间收益']} / 近1年 {r['近1年收益']}")

    print("\n" + "=" * 78)
    print(f"000063 中兴通讯 · 三模式对比   区间 {START} ~ {END}   近1年 = {eq_window_label()}")
    print("=" * 78)
    print(f"{'模式':<6}{'全区间收益':>10}  {'全区间Sharpe':>12}  {'近1年收益':>10}  {'近1年回撤':>10}  {'交易':>6}  {'止损':>5}")
    print("-" * 78)
    for r in results:
        print(f"{r['模式']:<6}{r['全区间收益']:>10}  {r['全区间Sharpe']:>12}  {r['近1年收益']:>10}  {r['近1年回撤']:>10}  {r['交易数']:>6}  {r['止损']:>5}")
    print("=" * 78)
    print("解读：近1年收益是实盘视角（一年前买入到现在）")


def eq_window_label():
    return "2025-08-27 起"


if __name__ == '__main__':
    main()
