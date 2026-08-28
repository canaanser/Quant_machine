# -*- coding: utf-8 -*-
"""
负向形态做 T（减仓）实验 vs 纯死叉卖出
==============================================
验证老板假设：负向形态不卖出，而是按"重算的惩罚分"减仓（做 T 降成本）。
如果减仓能降低回撤/提升夏普（低位再接回），则有做 T 价值。

评分还原：惩罚分用信号强度 strength 重算（当时可得，无未来泄漏），
不用 meta.base_score（那是未来收益映射）。

模式：
  - plain        : 现状（纯死叉卖出 + 止盈止损）
  - bearish_t    : 死叉卖出不变 + 当日 bearish 形态按强度减仓 20%~50%
                   （减仓后持仓保留，等后续涨回——做 T 逻辑）

用法：
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


def bearish_penalty_score(ohlc, today, lookback=60):
    """还原惩罚分：当日 bearish 形态的信号强度 → 惩罚分 [0,1]
    无未来函数：只用信号强度（原子归一化均值），不用 meta.base_score"""
    if today not in ohlc.index:
        return 0.0
    today_pos = ohlc.index.get_loc(today)
    hist = ohlc.iloc[max(0, today_pos - lookback):today_pos + 1]
    if len(hist) < 5:
        return 0.0
    results = scan_patterns(hist, debug=False)
    today_str = today.strftime('%Y-%m-%d')
    penalty = 0.0
    for r in results:
        if (r.get('date', '')[:10] == today_str
                and r.get('category') == 'bearish'):
            penalty = max(penalty, float(r.get('strength', 0)))
    return penalty


def make_engine(strategy, mode, verbose=False):
    """plain: 现状 | bearish_t: 负向形态减仓（做 T）"""
    engine = BacktestPipeline(strategy, top_n=10, verbose=verbose)
    if mode == 'plain':
        return engine

    orig_sells = engine._execute_sells
    strategy._market_data = None  # run_one 里挂载

    def sells_with_t(self, holdings_dict, final_scores, market_data,
                     account, current_prices, today, hist_returns, hist_market):
        # 先算死叉触发（全卖，现状逻辑）
        exit_series = self.strategy.get_exit_signal(hist_returns, hist_market)
        sell_signals = [s for s, e in exit_series.items() if e]

        # 对每只持仓：算 bearish 惩罚分（仅对死叉未触发的做减仓）
        for symbol in list(holdings_dict.keys()):
            if symbol in sell_signals:
                continue  # 死叉已全卖，不叠加
            try:
                ohlc = market_data.get_ohlc(symbol)
                penalty = bearish_penalty_score(ohlc, today)
            except Exception:
                continue
            if penalty <= 0:
                continue
            # 减仓比例：惩罚分 0.2~0.5 → 减 20%~50%
            reduce_ratio = min(0.5, max(0.2, penalty))
            pos = holdings_dict[symbol]
            sell_volume = int(pos['shares'] * reduce_ratio / 100) * 100
            if sell_volume < 100:
                continue
            # 直接经 adapter 卖出（减仓，不走死叉全卖逻辑）
            order_id = self.adapter.place_order(symbol, 'SELL', sell_volume, trade_date=today)
            if not order_id.startswith('ERROR'):
                status = self.adapter.get_order_status(order_id)
                if status['status'] == 'FILLED':
                    self.performance_analyzer.record_trade({
                        'order_id': order_id,
                        'symbol': symbol,
                        'action': 'SELL',
                        'filled_volume': status['filled_volume'],
                        'filled_amount': status['filled_volume'] * status['filled_price'],
                        'commission': 0,
                        'fill_price': status['filled_price'],
                        'timestamp': pd.Timestamp(today)
                    })
        # 恢复原卖出逻辑（死叉全卖）
        return orig_sells(holdings_dict, final_scores, market_data,
                          account, current_prices, today, hist_returns, hist_market)

    import pandas as pd
    engine._execute_sells = sells_with_t.__get__(engine, type(engine))
    return engine


def run_one(tickers, start, end, mode):
    market_data = load_data(source='freestockdb', tickers=tickers,
                            start=start, end=end, frequency='1d', fq='qfq')
    if market_data is None or market_data.price is None or market_data.price.empty:
        print("❌ 数据加载失败，请检查 stockdb 服务 / 股票代码")
        sys.exit(1)
    strategy = TrendStrengthStrategy(short=5, long=20, verbose=False)
    strategy._market_data = market_data
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
    parser = argparse.ArgumentParser(description="负向形态做T减仓 vs 纯死叉卖出")
    parser.add_argument("--tickers", default="000063")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--source", default="freestockdb")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    print(f"▶ 对比实验: 纯死叉 vs 死叉+bearish减仓(做T) | {tickers} | {args.start}~{args.end}")

    print("▶ 第 1 轮: 纯死叉卖出（现状）...")
    plain, t1 = run_one(tickers, args.start, args.end, 'plain')
    print(f"  ✅ 完成 {t1:.1f}s 收益={plain['total_return']:.2%} 夏普={plain['sharpe']:.4f} 交易={plain['trades']}")

    print("▶ 第 2 轮: 死叉+bearish减仓(做T) ...")
    bt, t2 = run_one(tickers, args.start, args.end, 'bearish_t')
    print(f"  ✅ 完成 {t2:.1f}s 收益={bt['total_return']:.2%} 夏普={bt['sharpe']:.4f} 交易={bt['trades']}")

    lines = []
    lines.append("=" * 60)
    lines.append(f"负向形态做T减仓对比（{tickers} | {args.start}~{args.end}）")
    lines.append("惩罚分 = bearish 信号强度重算（无未来泄漏）| 减仓 20%~50%")
    lines.append("=" * 60)
    lines.append(f"{'指标':<14} {'纯死叉':>12} {'+做T减仓':>14} {'差值':>12}")
    for k in ['total_return', 'sharpe', 'max_drawdown', 'trades']:
        a, b = plain[k], bt[k]
        lines.append(f"{k:<14} {a:>12.4f} {b:>14.4f} {b-a:>+12.4f}")
    lines.append("")
    verdict = []
    if bt['sharpe'] > plain['sharpe']: verdict.append("夏普↑")
    if bt['total_return'] > plain['total_return']: verdict.append("收益↑")
    if bt['max_drawdown'] >= plain['max_drawdown']: verdict.append("回撤改善")
    if not verdict: verdict = ["无提升"]
    lines.append(f"结论: {', '.join(verdict)}")
    out_path = PROJECT_ROOT / "outputs" / "bearish_t_result.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding='utf-8')
    print("\n✅ 完成！完整对比已写入 outputs/bearish_t_result.txt")
    print(f"   夏普: {plain['sharpe']:.4f} → {bt['sharpe']:.4f} | 收益: {plain['total_return']:.2%} → {bt['total_return']:.2%}")


if __name__ == "__main__":
    main()
