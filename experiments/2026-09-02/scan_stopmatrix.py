# -*- coding: utf-8 -*-
"""
止损×止盈全网格扫描（2026-09-02 老板：8只新票 多吃几组看曲面）
用法（Windows）：python -B scripts/scan_stopmatrix.py [--tickers 603019,000977,...] [--gate multi]
输出：CSV 到 outputs/stopmatrix_8new.csv + 控制台打印
"""
import sys
import os
import io
import time
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

DEFAULT_TICKERS = ['603019', '000977', '600160', '002050', '002837',
                   '001979', '000786', '002791']  # 8只新票（老板 2026-09-02 扩池）


def main():
    import argparse
    parser = argparse.ArgumentParser(description="止损×止盈网格扫描")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--gate", choices=['none', 'week', 'month', 'multi'], default='multi')
    parser.add_argument("--start", default='2022-06-01')
    parser.add_argument("--end", default='2026-08-27')
    args = parser.parse_args()

    from core.data_loader import load_data
    from core.backtest import BacktestPipeline
    from core.strategy import SimpleStrategy
    import logging as _logging
    _logging.disable(_logging.CRITICAL)  # 吞数据加载 INFO 刷屏（老板：只留聚合结果）

    tickers = [t.strip().zfill(6) for t in args.tickers.split(',') if t.strip()]
    gate = None if args.gate == 'none' else args.gate

    print(f"🚀 加载 {len(tickers)} 只: {args.start} ~ {args.end} ...")
    md = load_data(source='freestockdb', tickers=tickers,
                   start=args.start, end=args.end, frequency='1d', fq='qfq')

    rows = []
    print("\n止损,止盈,累计,近2年,近1年,Sharpe,最大回撤,交易数", flush=True)
    for sl in [None, 0.05, 0.08, 0.10, 0.15, 0.20]:
        for tp in [None, 0.20, 0.30, 0.40, 0.45, 0.50, 0.60]:
            t0 = time.time()
            st = SimpleStrategy(5, 20)
            eng = BacktestPipeline(st, top_n=10, risk_config={}, verbose=False,
                                   stop_loss_pct=sl, take_profit_pct=tp,
                                   trend_gate=gate)
            if gate == 'multi':
                eng.trend_gate_threshold = 2
            # 吞掉引擎的交易明细打印，只留聚合结果（2026-09-02 老板：打印太多贴不了）
            with contextlib.redirect_stdout(io.StringIO()):
                eng.run(md, initial_cash=500000, auto_save=False)
            eq = eng.equity_curve
            w1 = eq[eq.index >= (eq.index[-1] - pd.DateOffset(years=1))]
            w2 = eq[eq.index >= (eq.index[-1] - pd.DateOffset(years=2))]
            r1 = w1.iloc[-1] / w1.iloc[0] - 1 if len(w1) > 5 else float('nan')
            r2 = w2.iloc[-1] / w2.iloc[0] - 1 if len(w2) > 5 else float('nan')
            print(f"止损{sl or 0},止盈{tp or 0},{eng.total_return:+.3f},{r2:+.3f},{r1:+.3f},"
                  f"{eng.sharpe:.2f},{eng.max_drawdown:.3f},{len(eng.trades)}", flush=True)
            rows.append({'止损': sl or 0, '止盈': tp or 0,
                         '累计': eng.total_return, '近2年': r2, '近1年': r1,
                         'Sharpe': eng.sharpe, '回撤': eng.max_drawdown,
                         '交易': len(eng.trades), '耗时s': round(time.time() - t0)})

    out = os.path.join(ROOT, 'outputs', f'stopmatrix_{len(tickers)}only.csv')
    pd.DataFrame(rows).to_csv(out, index=False, encoding='utf-8-sig')
    print(f"\n💾 已存: {out}  （{len(rows)} 组）")


if __name__ == '__main__':
    main()
