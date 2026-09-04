# -*- coding: utf-8 -*-
"""回归基线重跑（2026-09-02 老板：Windows 跑，结果存文件）
对齐 test_backtest_regression.py 的场景：000063, 2025-01-01~2026-07-31, Simple 5/20, top10, 50万
输出：outputs/regression_baseline.json（当前权威行为）——用于更新 BASELINE 锁回归
用法（Windows）：python -B scripts/gen_baseline.py
"""
import sys
import io
import json
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    import logging as _logging
    _logging.disable(_logging.CRITICAL)
    from core.data_loader import load_data
    from core.backtest import BacktestPipeline
    from core.strategy import SimpleStrategy

    TICKER, START, END = "000063", "2025-01-01", "2026-07-31"
    print(f"🚀 跑回归基线: {TICKER} {START}~{END} Simple5/20 top10 50万")
    md = load_data(source='freestockdb', tickers=[TICKER], start=START, end=END,
                   frequency='1d', fq='qfq')
    st = SimpleStrategy(short=5, long=20)
    eng = BacktestPipeline(st, top_n=10, verbose=False)
    with contextlib.redirect_stdout(io.StringIO()):
        eng.run(md, initial_cash=500000)
    result = {
        "ticker": TICKER, "start": START, "end": END,
        "note": "2026-09-02 重跑基线（老板确认架构方向前锁定当前行为）",
        "total_return": eng.total_return,
        "annual_return": eng.annual_return,
        "sharpe": eng.sharpe,
        "max_drawdown": eng.max_drawdown,
        "trades": len(eng.trades),
        "equity_len": len(eng.equity_curve),
        "data_bars": md.price.shape[0],
    }
    out = ROOT / 'outputs' / 'regression_baseline.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print("\n✅ 基线已存: outputs/regression_baseline.json")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
