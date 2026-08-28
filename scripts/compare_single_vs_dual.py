# -*- coding: utf-8 -*-
"""
单腿（SimpleStrategy 抄底） vs 双腿（DualLegStrategy 抄底+趋势）组合对比
=====================================================================
2026-08-28 小二陈：验证双腿融合是否既保住 Simple 的抄底收益，又吃到趋势行情。
  单腿：死叉区跌势衰竭抄底（金叉区不买）——吃震荡，踏空趋势（2026 科技主升浪实锤）
  双腿：死叉区抄底腿 + 金叉区趋势腿（涨势加速顺势，涨势衰竭清仓），同一评分体系并存

用法（Windows，需 stockdb.exe 服务）：
    cd E:/stockgate/Quant_Alpha_System
    python scripts/compare_single_vs_dual.py
    python scripts/compare_single_vs_dual.py --tickers 000063,002396 --start 2025-01-01
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy, DualLegStrategy
import config.config as config_mod

START, END = '2017-01-01', '2026-08-27'
INITIAL_CASH = 500000
DEFAULT_TICKERS = list(config_mod.SCAN_TICKERS)


def run_one(name: str, strategy, tickers, start, end) -> dict:
    t0 = time.time()
    print(f"\n🚀 回测中（{name}，{len(tickers)} 只，{start} ~ {end}）...")
    market_data = load_data(
        source='freestockdb', tickers=tickers,
        start=start, end=end, frequency='1d', fq='qfq'
    )
    engine = BacktestPipeline(strategy, top_n=10, verbose=False)
    engine.run(market_data, initial_cash=INITIAL_CASH, auto_save=False)
    return {
        'strategy': name,
        'total_return': engine.total_return,
        'annual_return': engine.annual_return,
        'sharpe': engine.sharpe,
        'max_drawdown': engine.max_drawdown,
        'trades': len(engine.trades),
        'seconds': time.time() - t0,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="单腿 vs 双腿 组合对比回测")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    results = [
        run_one("Simple(抄底单腿)", SimpleStrategy(5, 20), tickers, args.start, args.end),
        run_one("DualLeg(抄底+趋势双腿)", DualLegStrategy(5, 20), tickers, args.start, args.end),
    ]

    print("\n" + "=" * 78)
    print(f"{'策略':<24}{'累计收益':>10}{'年化':>9}{'Sharpe':>9}{'最大回撤':>10}{'交易数':>8}{'耗时':>7}")
    print("-" * 78)
    for r in results:
        print(f"{r['strategy']:<24}{r['total_return']:>9.2%}{r['annual_return']:>8.2%}"
              f"{r['sharpe']:>9.2f}{r['max_drawdown']:>10.2%}{r['trades']:>8d}{r['seconds']:>6.1f}s")
    print("=" * 78)


if __name__ == "__main__":
    main()
