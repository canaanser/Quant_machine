# -*- coding: utf-8 -*-
"""
有约束 vs 无约束 · 回测对比脚本（速度测试版）
==============================================
用途：单只（默认）或多只股票，对比"无约束回测"与"位置权重约束回测"的绩效，
      并输出耗时，用于评估约束层接入的成本与收益。

约束逻辑（数据驱动 + 无未来函数）：
  - 位置代理：当日价格在"近120日区间"的位置（只用截至当日数据）
  - 权重映射（全量 20 只 3.5 年标定）：低位1.15 / 中低0.70 / 中高0.89 / 高位1.16
  - 回测中每次形态融合后，按当日位置权重乘到融合分数上

用法（Windows，数据走 stockdb SDK）：
    cd E:/stockgate/Quant_Alpha_System
    python tests/compare_constraint_backtest.py --tickers 000063
    python tests/compare_constraint_backtest.py --tickers 000063,600498 --start 2025-01-01 --end 2026-07-31

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

DEFAULT_START, DEFAULT_END = "2023-01-01", "2026-07-31"  # 全量 3.5 年
INITIAL_CASH = 500000


# ===== 位置权重（全量 20 只 3.5 年标定，数据驱动） =====
# 数据实证（34651 样本）：区间位置 0-0.25 → +1.16% | 0.25-0.5 → +0.27%
#   | 0.5-0.75 → +0.64% | 0.75-1.0 → +1.18%（两端强、中间弱）
# 权重 = 1 + 超额收益/2%，clip [0.4, 1.5]
RANGE_LOOKBACK = 120  # 近 120 日区间
RANGE_WEIGHTS = [
    (0.00, 0.25, 1.15),   # 低位（超跌/谷底）：加权
    (0.25, 0.50, 0.70),   # 中低（震荡）：降权
    (0.50, 0.75, 0.89),   # 中高（震荡上沿）：略降
    (0.75, 1.01, 1.16),   # 高位（突破新高）：加权
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


def run_one(tickers, start, end, apply_constraint, source='freestockdb'):
    market_data = load_data(source=source, tickers=tickers,
                            start=start, end=end, frequency='1d', fq='qfq')
    if market_data is None or market_data.price is None or market_data.price.empty:
        print("\n❌ 数据加载失败：返回空数据。请检查：")
        print("   1. stockdb 服务是否启动（127.0.0.1:7899）")
        print("   2. 股票代码是否正确（6位，如 000063）")
        print("   3. 该区间是否有数据")
        print("   4. 或改用 --source stockdb_http 走本地缓存（data/cache/stockdb/*.csv）")
        sys.exit(1)
    strategy = TrendStrengthStrategy(short=5, long=20, verbose=False)
    t0 = time.perf_counter()
    if apply_constraint:
        engine = make_constrained_engine(strategy)
    else:
        engine = BacktestPipeline(strategy, top_n=10, verbose=False)
    # 抑制交易明细打印（只保留核心指标），避免终端刷屏
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
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
    parser.add_argument("--source", default="freestockdb",
                        help="数据源：freestockdb(SDK) / stockdb_http(本地缓存)，默认 freestockdb")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    print(f"▶ 回测 {len(tickers)} 只: {tickers} | {args.start}~{args.end} | {args.source}")

    # 无约束
    print("▶ 第 1 轮：无约束 ...")
    base, t_base = run_one(tickers, args.start, args.end, False, source=args.source)
    print(f"  ✅ 完成 {t_base:.1f}s 收益={base['total_return']:.2%} 夏普={base['sharpe']:.4f}")

    # 有约束
    print("▶ 第 2 轮：有约束 ...")
    cons, t_cons = run_one(tickers, args.start, args.end, True, source=args.source)
    print(f"  ✅ 完成 {t_cons:.1f}s 收益={cons['total_return']:.2%} 夏普={cons['sharpe']:.4f}")

    # 对比
    lines = []
    lines.append("=" * 66)
    lines.append(f"有约束 vs 无约束 · 回测对比（{len(tickers)} 只: {tickers}）")
    lines.append(f"区间: {args.start} ~ {args.end} | 数据源: {args.source}")
    lines.append("约束: 价格近120日区间位置加权（低位1.15/中低0.70/中高0.89/高位1.16）")
    lines.append("=" * 66)
    lines.append(f"{'指标':<12} {'无约束':>12} {'有约束':>12} {'差值':>12}")
    for k in ['total_return', 'sharpe', 'max_drawdown', 'trades']:
        b, c = base[k], cons[k]
        lines.append(f"{k:<12} {b:>12.4f} {c:>12.4f} {c-b:>+12.4f}")
    lines.append("")
    lines.append(f"耗时: 无约束 {t_base:.1f}s | 有约束 {t_cons:.1f}s | 合计 {t_base+t_cons:.1f}s")
    lines.append(f"速度评估: 单只约 {(t_base+t_cons)/len(tickers):.1f}s/只 "
                 f"→ 10只约 {(t_base+t_cons)/len(tickers)*10:.0f}s, 20只约 {(t_base+t_cons)/len(tickers)*20:.0f}s")
    lines.append("")
    if cons['sharpe'] > base['sharpe']:
        lines.append("结论: 夏普率提升 ✅（约束方向正确）")
    else:
        lines.append("结论: 夏普率未提升 ❌（需调整权重或约束逻辑）")
    lines.append("⚠️ 注意: 权重映射为初步标定，正式接入需训练/测试分割校准。")
    report = "\n".join(lines)

    # 写文件（与终端共享目录，老板跑完我直接读）
    out_path = PROJECT_ROOT / "outputs" / "constraint_result.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding='utf-8')

    # 终端只显示精简结果
    print("\n✅ 回测完成！完整对比已写入 outputs/constraint_result.txt")
    print(f"   夏普: 无约束 {base['sharpe']:.4f} → 有约束 {cons['sharpe']:.4f} "
          f"({cons['sharpe']-base['sharpe']:+.4f})")
    print(f"   收益: 无约束 {base['total_return']:.2%} → 有约束 {cons['total_return']:.2%}")
    print(f"   交易: {base['trades']} → {cons['trades']}  耗时: {t_base+t_cons:.0f}s")


if __name__ == "__main__":
    main()
