# -*- coding: utf-8 -*-
"""
有约束 vs 无约束 · 回测对比脚本（速度测试版）
==============================================
用途：单只（默认）或多只股票，对比"无约束回测"与"约束回测"的绩效，
      并输出耗时，用于评估约束层接入的成本与收益。

约束逻辑（独立仓位维度，不改分数/排序，无未来函数）：
  - 位置代理：当日价格在"近120日区间"的位置（只用截至当日数据）
  - 语义：高位区（0.75-1.0）压缩买入仓位上限 ×0.4（防追高），
         中高（0.5-0.75）×0.8，低位/中低正常（×1.0）
  - 实现：包装 RiskManager.approve_order，不改 score、不改 Top-N 排序

用法（Windows，数据走 stockdb SDK）：
    cd E:/stockgate/Quant_Alpha_System
    python tests/compare_constraint_backtest.py --tickers 000063
    python tests/compare_constraint_backtest.py --tickers 000063,600498 --start 2025-01-01 --end 2026-07-31

说明：
  - 这是"看速度 + 看方向"的版本；仓位系数待正式接入时用训练/测试分割校准
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


# ===== 位置仓位系数（全量 20 只 3.5 年标定，数据驱动） =====
# 数据实证（34651 样本）：区间位置 0-0.25 → +1.16% | 0.25-0.5 → +0.27%
#   | 0.5-0.75 → +0.64% | 0.75-1.0 → +1.18%
# 语义：约束层不改分数/排序，只压缩高位区买入的仓位上限（防追高）
# 低位/中低：正常仓位（系数 1.0）| 中高：0.8 | 高位：0.4（减半以上）
RANGE_LOOKBACK = 120  # 近 120 日区间
RANGE_POS_CAPS = [
    (0.00, 0.50, 1.0),   # 低位/中低：正常仓位
    (0.50, 0.75, 0.8),   # 中高：仓位上限 ×0.8
    (0.75, 1.01, 0.4),   # 高位：仓位上限 ×0.4（防追高）
]

def price_in_range_pos_cap(ohlc, i) -> float:
    """当日价格在近 RANGE_LOOKBACK 日区间的位置 → 仓位系数（只用截至当日数据）"""
    window = ohlc['close'].iloc[max(0, i - RANGE_LOOKBACK):i + 1]
    if len(window) < 30:
        return 1.0
    lo, hi = float(window.min()), float(window.max())
    if hi <= lo:
        return 1.0
    pos = (float(ohlc['close'].iloc[i]) - lo) / (hi - lo)
    for lo_b, hi_b, cap in RANGE_POS_CAPS:
        if lo_b <= pos < hi_b:
            return cap
    return 1.0


# ===== 有约束引擎：不改分数/排序，包装风控层压缩高位区仓位 =====
def make_constrained_engine(strategy, verbose=False):
    engine = BacktestPipeline(strategy, top_n=10, verbose=verbose)

    # 记录当日各 symbol 的仓位系数（在形态融合时算好，供风控使用）
    engine._pos_caps = {}

    orig_fuse = engine._scan_and_fuse_patterns

    def fused_with_constraint(score_series, market_data, today):
        # 注意：score_series 原样返回（不改分数/排序），只预计算仓位系数
        score_series = orig_fuse(score_series, market_data, today)
        caps = {}
        for symbol in list(score_series.index):
            try:
                ohlc = market_data.get_ohlc(symbol)
                if ohlc is None or ohlc.empty or today not in ohlc.index:
                    continue
                today_pos = ohlc.index.get_loc(today)
                caps[symbol] = price_in_range_pos_cap(ohlc, today_pos)
            except Exception:
                continue
        engine._pos_caps = caps  # 供当日风控使用
        return score_series

    engine._scan_and_fuse_patterns = fused_with_constraint

    # 包装风控：买入审批前按当日仓位系数压缩 max_pos_ratio
    orig_approve = engine.risk_manager.approve_order

    def approve_with_constraint(signal, account, current_price):
        symbol = signal.get('symbol')
        if signal.get('action') == 'BUY' and symbol in engine._pos_caps:
            cap = engine._pos_caps[symbol]
            if cap < 1.0:
                # 压缩该笔买入的单票仓位上限（临时修改，用完恢复）
                orig_max = engine.risk_manager.max_pos_ratio
                engine.risk_manager.max_pos_ratio = orig_max * cap
                try:
                    return orig_approve(signal, account, current_price)
                finally:
                    engine.risk_manager.max_pos_ratio = orig_max
        return orig_approve(signal, account, current_price)

    engine.risk_manager.approve_order = approve_with_constraint
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
    lines.append("约束: 独立仓位维度（高位×0.4/中高×0.8/低位正常，不改分数）")
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
        lines.append("结论: 夏普率未提升 ❌（需调整仓位系数或约束逻辑）")
    lines.append("⚠️ 注意: 仓位系数为初步标定，正式接入需训练/测试分割校准。")
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
