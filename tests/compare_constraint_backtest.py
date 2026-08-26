# -*- coding: utf-8 -*-
"""
有约束 vs 无约束 · 回测对比脚本（速度测试版）
==============================================
用途：单只（默认）或多只股票，对比"无约束回测"与"位置权重约束回测"的绩效，
      并输出耗时，用于评估约束层接入的成本与收益。

约束逻辑（数据驱动 + 无未来函数）：
  - 位置代理：当日价格在"近120日区间"的位置（只用截至当日数据）
  - 权重映射（数据实证）：低位1.4 / 中低1.2 / 中高0.7 / 高位0.4
  - 回测中每次形态融合后，按当日位置权重乘到融合分数上

用法（Windows，数据走 stockdb SDK）：
    cd E:\stockgate\Quant_Alpha_System
    python tests\compare_constraint_backtest.py --tickers 000063
    python tests\compare_constraint_backtest.py --tickers 000063,600498 --start 2025-01-01 --end 2026-07-31

说明：
  - 这是"看速度 + 看方向"的版本；权重映射待正式接入时用训练/测试分割校准
"""
import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import TrendStrengthStrategy

DEFAULT_START, DEFAULT_END = "2025-01-01", "2026-07-31"
INITIAL_CASH = 500000


# ===== 位置权重（回测可用版：价格在近 N 日区间的位置，无未来函数） =====
# 数据实证（000063 一年，240 个形态触发日）：
#   区间位置 0.00-0.25 → +1.39% | 0.25-0.50 → +2.34% | 0.50-0.75 → -2.15% | 0.75-1.00 → -2.53%
# 权重映射：低位加权、高位降权（低买高卖）
RANGE_LOOKBACK = 120  # 近 120 日区间
RANGE_WEIGHTS = [
    (0.00, 0.25, 1.4),   # 低位：加权
    (0.25, 0.50, 1.2),
    (0.50, 0.75, 0.7),   # 高位：降权
    (0.75, 1.01, 0.4),
]

def price_in_range_weight(ohlc, i) -> float:
    """用当日价格在近 RANGE_LOOKBACK 日区间的位置映射权重（只用截至当日数据）"""
    window = ohlc['close'].iloc[max(0, i - RANGE_LOOKBACK):i + 1]
    if len(window) < 30:
        return 1.0
    lo, hi = float(window.min()), float(window.max())
    if hi <= lo:
        return 1.0
    pos = (float(ohlc['close'].iloc[i]) - lo) / (hi - lo)
    for lo_b, hi_b, w in RANGE_WEIGHTS:
        if lo_b <= pos < hi_b:
            return w
    return 1.0


# ===== 有约束引擎：包装 _scan_and_fuse_patterns =====
def make_constrained_engine(strategy, verbose=False):
    engine = BacktestPipeline(strategy, top_n=10, verbose=verbose)
    orig_fuse = engine._scan_and_fuse_patterns

    def fused_with_constraint(score_series, market_data, today):
        score_series = orig_fuse(score_series, market_data, today)
        for symbol in list(score_series.index):
            try:
                ohlc = market_data.get_ohlc(symbol)
                if ohlc is None or ohlc.empty or today not in ohlc.index:
                    continue
                today_pos = ohlc.index.get_loc(today)
                w = price_in_range_weight(ohlc, today_pos)
                if w != 1.0:
                    score_series[symbol] = score_series[symbol] * w
            except Exception:
                continue
        return score_series

    engine._scan_and_fuse_patterns = fused_with_constraint
    return engine


def run_one(tickers, start, end, apply_constraint):
    market_data = load_data(source='freestockdb', tickers=tickers,
                            start=start, end=end, frequency='1d', fq='qfq')
    strategy = TrendStrengthStrategy(short=5, long=20, verbose=False)
    t0 = time.perf_counter()
    if apply_constraint:
        engine = make_constrained_engine(strategy)
    else:
        engine = BacktestPipeline(strategy, top_n=10, verbose=False)
    engine.run(market_data, initial_cash=INITIAL_CASH)
    elapsed = time.perf_counter() - t0
    return {
        'total_return': engine.total_return,
        'annual_return': engine.annual_return,
        'sharpe': engine.sharpe,
        'max_drawdown': engine.max_drawdown,
        'trades': len(engine.trades),
    }, elapsed


def main():
    parser = argparse.ArgumentParser(description="有约束 vs 无约束回测对比（速度测试版）")
    parser.add_argument("--tickers", default="000063", help="股票代码，逗号分隔（默认 000063）")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    print("=" * 66)
    print(f"有约束 vs 无约束 · 回测对比（{len(tickers)} 只: {tickers}）")
    print(f"区间: {args.start} ~ {args.end}")
    print("约束: 价格近120日区间位置加权（低位1.4/中低1.2/中高0.7/高位0.4，无未来函数）")
    print("=" * 66)
    print()

    # 无约束
    print("▶ 第 1 轮：无约束回测 ...")
    base, t_base = run_one(tickers, args.start, args.end, False)
    print(f"  完成，耗时 {t_base:.1f}s")
    print(f"  累计收益: {base['total_return']:.2%}  夏普: {base['sharpe']:.4f}  "
          f"回撤: {base['max_drawdown']:.2%}  交易: {base['trades']}")
    print()

    # 有约束
    print("▶ 第 2 轮：有约束回测（位置权重） ...")
    cons, t_cons = run_one(tickers, args.start, args.end, True)
    print(f"  完成，耗时 {t_cons:.1f}s")
    print(f"  累计收益: {cons['total_return']:.2%}  夏普: {cons['sharpe']:.4f}  "
          f"回撤: {cons['max_drawdown']:.2%}  交易: {cons['trades']}")
    print()

    # 对比
    print("=" * 66)
    print("对比")
    print("=" * 66)
    print(f"{'指标':<12} {'无约束':>12} {'有约束':>12} {'差值':>12}")
    for k in ['total_return', 'sharpe', 'max_drawdown', 'trades']:
        b, c = base[k], cons[k]
        print(f"{k:<12} {b:>12.4f} {c:>12.4f} {c-b:>+12.4f}")
    print()
    print(f"耗时: 无约束 {t_base:.1f}s | 有约束 {t_cons:.1f}s | 合计 {t_base+t_cons:.1f}s")
    print(f"速度评估: 单只约 {(t_base+t_cons)/len(tickers):.1f}s/只 "
          f"→ 10只约 {(t_base+t_cons)/len(tickers)*10:.0f}s, 20只约 {(t_base+t_cons)/len(tickers)*20:.0f}s")
    print()
    if cons['sharpe'] > base['sharpe']:
        print("结论: 夏普率提升 ✅（约束方向正确）")
    else:
        print("结论: 夏普率未提升 ❌（需调整权重或约束逻辑）")
    print("⚠️ 注意: 权重映射为初步标定，正式接入需训练/测试分割校准。")


if __name__ == "__main__":
    main()
