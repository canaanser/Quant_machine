# -*- coding: utf-8 -*-
"""
技术面27只 加止损 样本外扫描（2026-09-02 老板：技术面选票有效，测止损能否压回撤）
配置：multi门，2025-01-01 空仓起步（2021起 warmup），只看 2025 起窗口
止损 6 档 × 止盈 7 档 = 42 组
用法（Windows）：python -B scripts/scan_oos_stoploss.py
"""
import sys
import io
import time
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

# 技术面合格 27 只（2026-09-02 样本外训练期选出，2024-12-31 视角）
TECH27 = ['002792', '300285', '002639', '300293', '688205', '600487', '301379',
          '002281', '600096', '002735', '603123', '002428', '002156', '300570',
          '600800', '301421', '002436', '002931', '000858', '000657', '000566',
          '002842', '600396', '002309', '600522', '688256', '600702']
START, END = '2021-01-01', '2026-08-27'
TRADE_START = '2025-01-01'


def main():
    import logging as _logging
    _logging.disable(_logging.CRITICAL)
    from core.data_loader import load_data
    from core.backtest import BacktestPipeline
    from core.strategy import SimpleStrategy

    md = load_data(source='freestockdb', tickers=TECH27, start=START, end=END,
                   frequency='1d', fq='qfq')
    print(f"🚀 技术面27只 {len(TECH27)} 只 | {START}~{END} | {TRADE_START} 空仓起步")
    rows = []
    print("\n止损,止盈,2025起收益,2025起回撤,Sharpe,2025起交易", flush=True)
    for sl in [None, 0.05, 0.08, 0.10, 0.15, 0.20]:
        for tp in [None, 0.20, 0.30, 0.40, 0.45, 0.50, 0.60]:
            t0 = time.time()
            st = SimpleStrategy(5, 20)
            eng = BacktestPipeline(st, top_n=10, risk_config={}, verbose=False,
                                   stop_loss_pct=sl, take_profit_pct=tp,
                                   trend_gate='multi')
            eng.trend_gate_threshold = 2
            with contextlib.redirect_stdout(io.StringIO()):
                eng.run(md, initial_cash=500000, auto_save=False, trade_start=TRADE_START)
            eq = eng.equity_curve
            seg = eq[eq.index >= pd.Timestamp(TRADE_START)]
            r = seg.iloc[-1] / seg.iloc[0] - 1 if len(seg) > 60 else float('nan')
            dd = (seg / seg.cummax() - 1).min() if len(seg) > 60 else float('nan')
            tr = eng.trades
            tr = tr[tr['Date'] >= pd.Timestamp(TRADE_START)] if not tr.empty else tr
            print(f"止损{sl or 0},止盈{tp or 0},{r:+.3f},{dd:.3f},{eng.sharpe:.2f},{len(tr)}", flush=True)
            rows.append({'止损': sl or 0, '止盈': tp or 0, '收益': r, '回撤': dd,
                         'Sharpe': eng.sharpe, '交易': len(tr)})
    out = ROOT / 'outputs' / 'oos_stoploss_tech27.csv'
    pd.DataFrame(rows).to_csv(out, index=False, encoding='utf-8-sig')
    print(f"\n💾 已存: {out}")


if __name__ == '__main__':
    main()
