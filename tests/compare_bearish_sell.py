# -*- coding: utf-8 -*-
"""
负向形态提前卖出 vs 纯死叉卖出 · 对比实验
==============================================
验证老板假设：如果负向（bearish）形态能比死叉更早给出卖出信号，
且提升胜率/收益/夏普，则应接入卖出侧。

模式：
  - plain        : 现状（纯死叉卖出 + 止盈止损）
  - bearish_sell : 死叉 + 当日出现 bearish 形态的持仓股提前卖出

用法（WSL 缓存或 Windows SDK 均可）：
    python tests/compare_bearish_sell.py --tickers 000063
    python tests/compare_bearish_sell.py --tickers 000063,600498 --start 2020-01-01 --end 2026-07-31
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
from structure_engine.scanner.pattern_scanner import scan_patterns

DEFAULT_START, DEFAULT_END = "2020-01-01", "2026-07-31"
INITIAL_CASH = 500000


def make_engine(strategy, mode, verbose=False):
    """plain: 现状 | bearish_sell: 负向形态提前卖出"""
    engine = BacktestPipeline(strategy, top_n=10, verbose=verbose)
    if mode == 'plain':
        return engine

    orig_sells = engine._execute_sells

    def sells_with_bearish(holdings_dict, sell_signals, final_scores, market_data,
                           account, current_prices, today, hist_returns, hist_market):
        # 对每只持仓股：当日是否出现 bearish 形态 → 提前加入卖出
        extra = []
        for symbol in holdings_dict:
            try:
                ohlc = market_data.get_ohlc(symbol)
                if ohlc is None or ohlc.empty or today not in ohlc.index:
                    continue
                today_pos = ohlc.index.get_loc(today)
                hist = ohlc.iloc[max(0, today_pos - 60):today_pos + 1]
                if len(hist) < 5:
                    continue
                results = scan_patterns(hist, debug=False)
                today_str = today.strftime('%Y-%m-%d')
                for r in results:
                    if (r.get('date', '')[:10] == today_str
                            and r.get('category') == 'bearish'
                            and r.get('strength', 0) > 0):
                        extra.append(symbol)
                        break
            except Exception:
                continue
        combined = list(set(sell_signals) | set(extra))
        return orig_sells(holdings_dict, combined, final_scores, market_data,
                          account, current_prices, today, hist_returns, hist_market)

    engine._execute_sells = sells_with_bearish
    return engine


def run_one(tickers, start, end, mode):
    market_data = load_data(source='freestockdb', tickers=tickers,
                            start=start, end=end, frequency='1d', fq='qfq')
    if market_data is None or market_data.price is None or market_data.price.empty:
        print("❌ 数据加载失败，请检查 stockdb 服务 / 股票代码")
        sys.exit(1)
    strategy = TrendStrengthStrategy(short=5, long=20, verbose=False)
    t0 = time.perf_counter()
    engine = make_engine(strategy, mode)
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
    parser = argparse.ArgumentParser(description="负向形态提前卖出 vs 纯死叉卖出")
    parser.add_argument("--tickers", default="000063")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--source", default="freestockdb")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    print(f"▶ 对比实验: 纯死叉卖出 vs 负向形态提前卖出 | {tickers} | {args.start}~{args.end}")

    print("▶ 第 1 轮: 纯死叉卖出（现状）...")
    plain, t1 = run_one(tickers, args.start, args.end, 'plain')
    print(f"  ✅ 完成 {t1:.1f}s 收益={plain['total_return']:.2%} 夏普={plain['sharpe']:.4f} 交易={plain['trades']}")

    print("▶ 第 2 轮: 死叉+bearish形态提前卖出 ...")
    bsell, t2 = run_one(tickers, args.start, args.end, 'bearish_sell')
    print(f"  ✅ 完成 {t2:.1f}s 收益={bsell['total_return']:.2%} 夏普={bsell['sharpe']:.4f} 交易={bsell['trades']}")

    lines = []
    lines.append("=" * 60)
    lines.append(f"负向形态提前卖出对比（{tickers} | {args.start}~{args.end}）")
    lines.append("=" * 60)
    lines.append(f"{'指标':<14} {'纯死叉':>12} {'+bearish卖出':>14} {'差值':>12}")
    for k in ['total_return', 'sharpe', 'max_drawdown', 'trades']:
        a, b = plain[k], bsell[k]
        lines.append(f"{k:<14} {a:>12.4f} {b:>14.4f} {b-a:>+12.4f}")
    lines.append("")
    verdict = []
    if bsell['sharpe'] > plain['sharpe']: verdict.append("夏普↑")
    if bsell['total_return'] > plain['total_return']: verdict.append("收益↑")
    if bsell['max_drawdown'] >= plain['max_drawdown']: verdict.append("回撤改善")
    if not verdict:
        verdict = ["无提升"]
    lines.append(f"结论: {', '.join(verdict)}")
    out_path = PROJECT_ROOT / "outputs" / "bearish_sell_result.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding='utf-8')
    print("\n✅ 完成！完整对比已写入 outputs/bearish_sell_result.txt")
    print(f"   夏普: {plain['sharpe']:.4f} → {bsell['sharpe']:.4f} | 收益: {plain['total_return']:.2%} → {bsell['total_return']:.2%}")


if __name__ == "__main__":
    main()
