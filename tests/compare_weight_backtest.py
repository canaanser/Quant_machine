"""
权重来源对比回测（强化版 TrendStrengthStrategy）
==============================================
一键对比：同一策略分别用 现有权重表(legacy) 和 数据驱动权重表(data) 跑回测，
输出四个核心指标对比，用数据决定权重表是否切换。

用法（Windows，数据走 stockdb SDK）：
    cd E:/stockgate/Quant_Alpha_System
    python tests/compare_weight_backtest.py

说明：
  - 策略：TrendStrengthStrategy（趋势强度，短5/长20）
  - 标的：中兴通讯 000063，区间 2023-01-01 ~ 2026-08-19
  - 权重来源切换通过修改 config.config.WEIGHT_SOURCE 实现（回测融合处函数内
    import 每次读取最新值，无需改文件）
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import TrendStrengthStrategy
import config.config as config_mod

START, END = '2023-01-01', '2026-08-19'
INITIAL_CASH = 500000
TICKERS = ['000063']


def run_one(weight_source: str, tickers=None, start=None, end=None) -> dict:
    """用指定权重来源跑一次回测，返回指标"""
    tickers = tickers or TICKERS
    start = start or START
    end = end or END
    config_mod.WEIGHT_SOURCE = weight_source  # 回测融合处每次读取最新值

    print(f"\n🚀 回测中（权重来源 = {weight_source}）...")
    market_data = load_data(
        source='freestockdb',
        tickers=tickers,
        start=start,
        end=end,
        frequency='1d',
        fq='qfq'
    )
    strategy = TrendStrengthStrategy(short=5, long=20, verbose=False)
    engine = BacktestPipeline(strategy, top_n=10, verbose=False)
    engine.run(market_data, initial_cash=INITIAL_CASH)

    return {
        'weight_source': weight_source,
        'total_return': engine.total_return,
        'annual_return': engine.annual_return,
        'sharpe': engine.sharpe,
        'max_drawdown': engine.max_drawdown,
        'trades': len(engine.trades),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="权重来源对比回测（强化版 TrendStrengthStrategy）")
    parser.add_argument("--tickers", default="000063", help="股票代码，逗号分隔（默认 000063）")
    parser.add_argument("--start", default=START, help="起始日期（默认 2023-01-01）")
    parser.add_argument("--end", default=END, help="结束日期（默认 2026-08-19）")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    start, end = args.start, args.end

    print("=" * 66)
    print("权重来源对比回测 · 强化版 TrendStrengthStrategy")
    print(f"标的: {tickers} | 区间: {start} ~ {end}")
    print("=" * 66)

    results = [run_one(ws, tickers, start, end) for ws in ['legacy', 'data']]

    # 恢复默认权重来源
    config_mod.WEIGHT_SOURCE = 'legacy'

    print("\n" + "=" * 66)
    print("📊 对比结果")
    print("=" * 66)
    print(f"{'指标':<14}{'现有权重(legacy)':>18}{'数据权重(data)':>18}{'差异':>12}")
    rows = [
        ('累计收益率', 'total_return', '{:+.2%}'),
        ('年化收益率', 'annual_return', '{:+.2%}'),
        ('夏普比率', 'sharpe', '{:+.3f}'),
        ('最大回撤', 'max_drawdown', '{:.2%}'),
        ('交易次数', 'trades', '{:d}'),
    ]
    for label, key, fmt in rows:
        v1 = results[0][key]
        v2 = results[1][key]
        diff = v2 - v1
        diff_fmt = '{:+.2%}'.format(diff) if key not in ('trades',) else '{:+d}'.format(int(diff))
        if key == 'sharpe':
            diff_fmt = '{:+.3f}'.format(diff)
        print(f"{label:<14}{fmt.format(v1):>18}{fmt.format(v2):>18}{diff_fmt:>12}")

    print("\n" + "=" * 66)
    # 简单结论
    r1, r2 = results[0], results[1]
    better = []
    if r2['total_return'] > r1['total_return']:
        better.append('累计收益更高')
    if r2['max_drawdown'] < r1['max_drawdown']:
        better.append('回撤更小')
    if r2['sharpe'] > r1['sharpe']:
        better.append('夏普更高')
    if better:
        print(f"数据权重(data)在: {'、'.join(better)} 方面更优")
    else:
        print("现有权重(legacy)全面占优，或差异不显著")
    print("（注：单只股票单区间结果，切换权重前建议多标的/多区间复验）")
    print("=" * 66)


if __name__ == "__main__":
    main()
