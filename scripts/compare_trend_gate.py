# -*- coding: utf-8 -*-
"""
趋势线过滤器对比实验（2026-08-30 老板：做法二/三，关止损测）
================================================================
对比：无门 / 周线门 / 月线门 / multi(≥2级)
指标：累计、近1年、近2年、Sharpe、最大回撤、交易数

用法（Windows，stockdb 服务运行）：
    python -B scripts/compare_trend_gate.py            # 84池 + 精选15
    python -B scripts/compare_trend_gate.py --pool 84  # 只跑 84 池
    python -B scripts/compare_trend_gate.py --pool curated
"""
import argparse
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy
import config.config as cfg

START, END = '2022-06-01', '2026-08-27'
GATES = [None, 'week', 'month', 'multi']
POOLS = {
    '84': ('84池', lambda: list(cfg.SCAN_TICKERS)),
    'curated': ('精选15', lambda: list(cfg.SCAN_TICKERS_CURATED)),
}


def run_one(md, tickers, gate, threshold=2):
    st = SimpleStrategy(5, 20)
    eng = BacktestPipeline(st, top_n=10, risk_config={}, verbose=False,
                           stop_loss_pct=None, trend_gate=gate)
    if gate == 'multi':
        eng.trend_gate_threshold = threshold
    eng.run(md, initial_cash=500000, auto_save=False)
    eq = eng.equity_curve
    w1 = eq[eq.index >= (eq.index[-1] - pd.DateOffset(years=1))]
    w2 = eq[eq.index >= (eq.index[-1] - pd.DateOffset(years=2))]
    return {
        'gate': gate or '无门',
        '累计': eng.total_return,
        '近1年': w1.iloc[-1] / w1.iloc[0] - 1 if len(w1) > 5 else float('nan'),
        '近2年': w2.iloc[-1] / w2.iloc[0] - 1 if len(w2) > 5 else float('nan'),
        'Sharpe': eng.sharpe,
        '最大回撤': eng.max_drawdown,
        '交易数': len(eng.trades),
    }


def main():
    parser = argparse.ArgumentParser(description="趋势线过滤器对比")
    parser.add_argument("--pool", choices=['84', 'curated', 'both'], default='both')
    args = parser.parse_args()

    pools = [('84', POOLS['84'])] if args.pool == '84' else (
        [('curated', POOLS['curated'])] if args.pool == 'curated' else list(POOLS.items()))

    for key, (pname, getter) in pools:
        tickers = getter()
        print(f"\n{'='*70}\n📦 {pname}（{len(tickers)} 只，关止损，{START}~{END}）\n{'='*70}")
        t0 = time.time()
        md_pool = load_data(source='freestockdb', tickers=tickers,
                            start=START, end=END, frequency='1d', fq='qfq')
        print(f"数据加载 {time.time()-t0:.0f}s，{md_pool.price.shape[0]} 交易日")
        rows = []
        for gate in GATES:
            t1 = time.time()
            r = run_one(md_pool, tickers, gate)
            rows.append(r)
            print(f"  [{gate or '无门':5s}] 完成 {time.time()-t1:.0f}s  "
                  f"累计{r['累计']:+.1%} 近1年{r['近1年']:+.1%} 近2年{r['近2年']:+.1%} "
                  f"Sharpe{r['Sharpe']:.2f} 回撤{r['最大回撤']:.1%} 交易{r['交易数']}")
        df = pd.DataFrame(rows).set_index('gate')
        print("\n===== 汇总表 =====")
        for col in ['累计', '近1年', '近2年', 'Sharpe', '最大回撤', '交易数']:
            if col in ('累计', '近1年', '近2年', '最大回撤'):
                df[col] = df[col].map(lambda v: f"{v:+.1%}")
            elif col == 'Sharpe':
                df[col] = df[col].map(lambda v: f"{v:.2f}")
        print(df.to_string())


if __name__ == "__main__":
    main()
