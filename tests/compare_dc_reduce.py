# -*- coding: utf-8 -*-
"""
乌云盖顶减仓规则 · 回测验证（叠加在双均线策略上）
==============================================
数据实证信号：从波峰快速深跌（回撤>20% + 下跌<30天）+ 出现乌云盖顶
→ D+5 平均 -3.35%，胜率仅 34% → 应减仓防守。

模式：
  - plain        : 现状（双均线 + 形态融合 + 死叉卖出）
  - dc_reduce    : 现状 + "深跌乌云盖顶 → 减仓30%"规则（不改分数/排序）

触发条件（全部实盘当下可算，无未来函数）：
  持仓股当日：
    1) 近120日回撤 > 20%
    2) 距波峰下跌 < 30 天
    3) 当日出现乌云盖顶形态
  → 减仓 30%（不足100股则跳过）

用法：
    python tests/compare_dc_reduce.py --tickers 000063 --start 2020-01-01 --end 2026-07-31
结果写入 outputs/dc_reduce_result.txt
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
LOOKBACK = 120
REDUCE_RATIO = 0.30
DD_THRESHOLD = -0.20      # 回撤 > 20%
DAYS_THRESHOLD = 30       # 下跌 < 30天


def trigger_dc_reduce(ohlc, today):
    """判断是否触发乌云盖顶减仓：深跌(<30天) + 乌云盖顶
    返回 True/False，全部用截至当日数据（无未来函数）"""
    if today not in ohlc.index:
        return False
    today_pos = ohlc.index.get_loc(today)
    if today_pos < 30:
        return False
    base = float(ohlc['close'].iloc[today_pos])
    if base <= 0:
        return False
    # 1) 近120日回撤
    window = ohlc['close'].iloc[max(0, today_pos - LOOKBACK):today_pos + 1]
    peak = float(window.max())
    if peak <= 0:
        return False
    drawdown = base / peak - 1
    if drawdown > DD_THRESHOLD:
        return False
    # 2) 距波峰下跌天数
    peak_global = window.idxmax()
    days_since_peak = (today - peak_global).days
    if days_since_peak >= DAYS_THRESHOLD:
        return False
    # 3) 当日出现乌云盖顶
    hist = ohlc.iloc[max(0, today_pos - 60):today_pos + 1]
    if len(hist) < 5:
        return False
    results = scan_patterns(hist, debug=False)
    today_str = today.strftime('%Y-%m-%d')
    for r in results:
        if (r.get('date', '')[:10] == today_str
                and '乌云' in r.get('pattern_type', '')
                and r.get('strength', 0) > 0):
            return True
    return False


def make_engine(strategy, mode, verbose=False):
    engine = BacktestPipeline(strategy, top_n=10, verbose=verbose)
    if mode == 'plain':
        return engine

    orig_sells = engine._execute_sells

    def sells_with_dc(self, holdings_dict, final_scores, market_data,
                      account, current_prices, today, hist_returns, hist_market):
        # 先执行原卖出逻辑（死叉）
        result = orig_sells(holdings_dict, final_scores, market_data,
                            account, current_prices, today, hist_returns, hist_market)
        # 再叠加乌云盖顶减仓（对仍持仓的股票）
        for symbol in list(holdings_dict.keys()):
            try:
                ohlc = market_data.get_ohlc(symbol)
                if ohlc is None or ohlc.empty:
                    continue
                if not trigger_dc_reduce(ohlc, today):
                    continue
                # 减仓：查当前持仓（adapter 里的最新状态）
                acc = self.adapter.get_account_info()
                pos = next((p for p in acc.positions if p.symbol == symbol), None)
                if pos is None or pos.shares <= 0:
                    continue
                sell_volume = int(pos.shares * REDUCE_RATIO / 100) * 100
                if sell_volume < 100:
                    continue
                order_id = self.adapter.place_order(symbol, 'SELL', sell_volume, trade_date=today)
                if not order_id.startswith('ERROR'):
                    status = self.adapter.get_order_status(order_id)
                    if status['status'] == 'FILLED':
                        import pandas as _pd
                        self.performance_analyzer.record_trade({
                            'order_id': order_id,
                            'symbol': symbol,
                            'action': 'SELL',
                            'filled_volume': status['filled_volume'],
                            'filled_amount': status['filled_volume'] * status['filled_price'],
                            'commission': 0,
                            'fill_price': status['filled_price'],
                            'timestamp': _pd.Timestamp(today)
                        })
            except Exception:
                continue
        return result

    engine._execute_sells = sells_with_dc.__get__(engine, type(engine))
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
    parser = argparse.ArgumentParser(description="乌云盖顶减仓规则回测验证")
    parser.add_argument("--tickers", default="000063")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--source", default="freestockdb")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    print(f"▶ 对比: 现状 vs +乌云盖顶减仓 | {tickers} | {args.start}~{args.end}")
    print(f"   规则: 回撤>20% + 下跌<{DAYS_THRESHOLD}天 + 乌云盖顶 → 减仓{REDUCE_RATIO:.0%}")

    print("▶ 第 1 轮: 现状 ...")
    plain, t1 = run_one(tickers, args.start, args.end, 'plain')
    print(f"  ✅ {t1:.0f}s 收益={plain['total_return']:.2%} 夏普={plain['sharpe']:.4f} 交易={plain['trades']}")

    print("▶ 第 2 轮: +乌云盖顶减仓 ...")
    dc, t2 = run_one(tickers, args.start, args.end, 'dc_reduce')
    print(f"  ✅ {t2:.0f}s 收益={dc['total_return']:.2%} 夏普={dc['sharpe']:.4f} 交易={dc['trades']}")

    lines = []
    lines.append("=" * 60)
    lines.append(f"乌云盖顶减仓规则回测（{tickers} | {args.start}~{args.end}）")
    lines.append(f"规则: 回撤>{abs(DD_THRESHOLD):.0%} + 下跌<{DAYS_THRESHOLD}天 + 乌云盖顶 → 减仓{REDUCE_RATIO:.0%}")
    lines.append("=" * 60)
    lines.append(f"{'指标':<14} {'现状':>12} {'+乌云减仓':>14} {'差值':>12}")
    for k in ['total_return', 'sharpe', 'max_drawdown', 'trades']:
        a, b = plain[k], dc[k]
        lines.append(f"{k:<14} {a:>12.4f} {b:>14.4f} {b-a:>+12.4f}")
    lines.append("")
    verdict = []
    if dc['sharpe'] > plain['sharpe']: verdict.append("夏普↑")
    if dc['total_return'] > plain['total_return']: verdict.append("收益↑")
    if dc['max_drawdown'] >= plain['max_drawdown']: verdict.append("回撤改善")
    if not verdict: verdict = ["无提升"]
    lines.append(f"结论: {', '.join(verdict)}")
    out_path = PROJECT_ROOT / "outputs" / "dc_reduce_result.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding='utf-8')
    print("\n✅ 完成！结果写入 outputs/dc_reduce_result.txt")
    print(f"   夏普: {plain['sharpe']:.4f} → {dc['sharpe']:.4f} | 收益: {plain['total_return']:.2%} → {dc['total_return']:.2%}")


if __name__ == "__main__":
    main()
