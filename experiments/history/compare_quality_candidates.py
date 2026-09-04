# -*- coding: utf-8 -*-
"""
穷举器候选规则回测对比（84 只主池）
=====================================================================
2026-08-28 小二陈：signal_enum 五道闸门选出候选，回测验证组合层面表现。
  配置1：v1 基线（深跌-20% 放量0.7，penalty 0.1）= 已知 857.43%/0.58
  配置2：深跌-20% 放量0.9（穷举器最佳候选，样本外67.5%/2.21 无衰减）
  配置3：深跌-20% 放量0.9 + 位置-40%（更严，样本外65.5%附近，稳健型）

用法（Windows，需 stockdb.exe 服务，务必 python -B 防缓存）：
    cd E:/stockgate/Quant_Alpha_System
    python -B scripts/compare_quality_candidates.py
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


def run_one(name, deep, vol, pos_high, tickers, market_data):
    t0 = time.time()
    strategy = SimpleStrategy(5, 20, quality_filter=True, quality_deep=deep,
                              quality_vol=vol, quality_penalty=0.1,
                              quality_pos_high=pos_high, quality_pos_range=1.0)
    eng = BacktestPipeline(strategy, top_n=10, verbose=False)
    eng.run(market_data, initial_cash=INITIAL_CASH, auto_save=False)
    return {'strategy': name, 'total': eng.total_return, 'annual': eng.annual_return,
            'sharpe': eng.sharpe, 'mdd': eng.max_drawdown, 'trades': len(eng.trades),
            'sec': time.time() - t0}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="穷举器候选规则回测对比")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    print(f"🚀 数据加载：{len(tickers)} 只 ...")
    md = load_data(source='freestockdb', tickers=tickers,
                   start=args.start, end=args.end, frequency='1d', fq='qfq')
    print(f"✅ 加载完成 {md.price.shape[0]} 交易日")

    configs = [
        ("v1基线(深跌20+放量0.7)", -0.20, 0.7, 0.0),
        ("候选:放量0.9", -0.20, 0.9, 0.0),
        ("候选:放量0.9+位置-40%", -0.20, 0.9, -0.40),
    ]
    results = []
    for name, d, v, p in configs:
        print(f"\n🚀 {name} ...")
        results.append(run_one(name, d, v, p, tickers, md))
        print(f"  ✅ {results[-1]['strategy']}: 累计 {results[-1]['total']:.2%} "
              f"Sharpe {results[-1]['sharpe']:.2f} 回撤 {results[-1]['mdd']:.2%} "
              f"交易 {results[-1]['trades']} 耗时 {results[-1]['sec']:.1f}s", flush=True)

    print("\n" + "=" * 78)
    print(f"{'配置':<26}{'累计收益':>10}{'年化':>9}{'Sharpe':>9}{'最大回撤':>10}{'交易数':>8}")
    print("-" * 78)
    for r in results:
        print(f"{r['strategy']:<26}{r['total']:>9.2%}{r['annual']:>8.2%}"
              f"{r['sharpe']:>9.2f}{r['mdd']:>10.2%}{r['trades']:>8d}")
    print("=" * 78)


if __name__ == "__main__":
    main()
