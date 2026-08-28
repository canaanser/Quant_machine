# -*- coding: utf-8 -*-
"""
双均线金叉（SimpleStrategy·二阶衰竭） vs 趋势强度（TrendStrengthStrategy）组合对比回测
==================================================================================
背景（2026-08-28 小二陈）：
  老板单票验证发现 SimpleStrategy 在 000063（2025-08~2026-08）大幅跑赢
  TrendStrengthStrategy（+23.2% vs -2.4%），归因"用了二阶指标"（MA5 斜率之斜率
  = 加速度拐点：死叉区跌势衰竭抄底、金叉区涨势衰竭清仓）。
  本脚本把两者放到同一股票池、同一区间做组合对比，判定是"个股运气"还是"组合真金"。

用法（Windows，数据走 stockdb SDK，需 stockdb.exe 服务运行）：
    cd E:/stockgate/Quant_Alpha_System
    python scripts/compare_simple_vs_trend.py                    # 84 只主池 2017~今
    python scripts/compare_simple_vs_trend.py --tickers 000063   # 单票复现老板结果
    python scripts/compare_simple_vs_trend.py --start 2025-08-28 --end 2026-08-27 --tickers 000063

输出：两策略的 累计/年化/Sharpe/最大回撤/交易数 对比表。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy, TrendStrengthStrategy
import config.config as config_mod

START, END = '2017-01-01', '2026-08-27'
INITIAL_CASH = 500000
DEFAULT_TICKERS = list(config_mod.SCAN_TICKERS)  # 84 只主池


def run_one(name: str, strategy, tickers, start, end) -> dict:
    print(f"\n🚀 回测中（策略 = {name}，{len(tickers)} 只，{start} ~ {end}）...")
    market_data = load_data(
        source='freestockdb',
        tickers=tickers,
        start=start,
        end=end,
        frequency='1d',
        fq='qfq'
    )
    engine = BacktestPipeline(strategy, top_n=10, verbose=False)
    engine.run(market_data, initial_cash=INITIAL_CASH)

    return {
        'strategy': name,
        'total_return': engine.total_return,
        'annual_return': engine.annual_return,
        'sharpe': engine.sharpe,
        'max_drawdown': engine.max_drawdown,
        'trades': len(engine.trades),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="双均线金叉 vs 趋势强度 组合对比回测")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS),
                        help="股票代码，逗号分隔（默认 84 只主池）")
    parser.add_argument("--start", default=START, help="起始日期（默认 2017-01-01）")
    parser.add_argument("--end", default=END, help="结束日期（默认 2026-08-27）")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    results = [
        run_one("SimpleStrategy(双均线金叉)", SimpleStrategy(short=5, long=20),
                tickers, args.start, args.end),
        run_one("TrendStrengthStrategy(趋势强度)", TrendStrengthStrategy(short=5, long=20),
                tickers, args.start, args.end),
    ]

    print("\n" + "=" * 74)
    print(f"{'策略':<32}{'累计收益':>10}{'年化':>9}{'Sharpe':>9}{'最大回撤':>10}{'交易数':>8}")
    print("-" * 74)
    for r in results:
        print(f"{r['strategy']:<32}{r['total_return']:>9.2%}{r['annual_return']:>8.2%}"
              f"{r['sharpe']:>9.2f}{r['max_drawdown']:>10.2%}{r['trades']:>8d}")
    print("=" * 74)


if __name__ == "__main__":
    main()
