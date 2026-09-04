# -*- coding: utf-8 -*-
"""
Simple 原版 vs 质量评分过滤 三模式对比（84 只主池）
=====================================================================
2026-08-28 小二陈：事前质量评分规则"深跌<-20%+放量>0.7"（84只样本外
10日胜率65.1%/Sharpe2.18）已验证，现上策略层对比三种接入方式：
  1. 原版：Simple 原评分（全部信号，覆盖广）
  2. 降权：不满足规则的信号评分×0.2（轻仓试探，保留覆盖面）
  3. 跳过：不满足规则的信号直接置 0（只做高质量信号）

用法（Windows，需 stockdb.exe 服务）：
    cd E:/stockgate/Quant_Alpha_System
    python scripts/compare_simple_quality.py
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
    parser = argparse.ArgumentParser(description="Simple 原版 vs 质量评分过滤三模式")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    results = [
        run_one("Simple 原版", SimpleStrategy(5, 20), tickers, args.start, args.end),
        run_one("Simple+质量降权(×0.2)", SimpleStrategy(5, 20, quality_filter=True, quality_penalty=0.2),
                tickers, args.start, args.end),
        run_one("Simple+质量跳过(只做高质量)", SimpleStrategy(5, 20, quality_filter=True, quality_penalty=0.0),
                tickers, args.start, args.end),
    ]

    print("\n" + "=" * 78)
    print(f"{'策略':<26}{'累计收益':>10}{'年化':>9}{'Sharpe':>9}{'最大回撤':>10}{'交易数':>8}{'耗时':>7}")
    print("-" * 78)
    for r in results:
        print(f"{r['strategy']:<26}{r['total_return']:>9.2%}{r['annual_return']:>8.2%}"
              f"{r['sharpe']:>9.2f}{r['max_drawdown']:>10.2%}{r['trades']:>8d}{r['seconds']:>6.1f}s")
    print("=" * 78)


if __name__ == "__main__":
    main()
