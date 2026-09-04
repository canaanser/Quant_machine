# -*- coding: utf-8 -*-
"""
质量降权 penalty 扫描：找最优降权力度
=====================================================================
2026-08-28 小二陈：质量降权（penalty=0.2）已验证有效（Sharpe 0.51→0.64），
本脚本扫描 penalty ∈ {0.0跳过, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0原版}，
看 Sharpe/收益/回撤 随降权力度的变化，找最优平衡点。

用法（Windows，需 stockdb.exe 服务）：
    cd E:/stockgate/Quant_Alpha_System
    python scripts/scan_quality_penalty.py
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
PENALTIES = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]


def main():
    import argparse
    parser = argparse.ArgumentParser(description="质量降权 penalty 扫描")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    print(f"🚀 数据加载：{len(tickers)} 只 ...")
    market_data = load_data(
        source='freestockdb', tickers=tickers,
        start=args.start, end=args.end, frequency='1d', fq='qfq'
    )
    print(f"✅ 加载完成 {market_data.price.shape[0]} 交易日")

    results = []
    for p in PENALTIES:
        label = "跳过(0.0)" if p == 0.0 else ("原版(1.0)" if p >= 1.0 else f"降权×{p}")
        t0 = time.time()
        strategy = SimpleStrategy(5, 20, quality_filter=(p < 1.0), quality_penalty=p)
        eng = BacktestPipeline(strategy, top_n=10, verbose=False)
        eng.run(market_data, initial_cash=INITIAL_CASH, auto_save=False)
        results.append((label, eng, time.time() - t0))
        print(f"  ✅ {label}: 累计 {eng.total_return:.2%} Sharpe {eng.sharpe:.2f} 回撤 {eng.max_drawdown:.2%} "
              f"交易 {len(eng.trades)} 耗时 {time.time()-t0:.1f}s", flush=True)

    print("\n" + "=" * 74)
    print(f"{'降权':<12}{'累计收益':>10}{'年化':>9}{'Sharpe':>9}{'最大回撤':>10}{'交易数':>8}")
    print("-" * 74)
    for label, eng, _ in results:
        print(f"{label:<12}{eng.total_return:>9.2%}{eng.annual_return:>8.2%}"
              f"{eng.sharpe:>9.2f}{eng.max_drawdown:>10.2%}{len(eng.trades):>8d}")
    print("=" * 74)
    print("注：Sharpe 最高且回撤可控的档位 = 最优降权力度；回撤过大的档位需谨慎（集中度风险）")


if __name__ == "__main__":
    main()
