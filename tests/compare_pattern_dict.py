# -*- coding: utf-8 -*-
"""
形态×位置强弱字典 回测实验
==============================================
验证老板理念：形态只分强弱不分方向，强弱由"形态×位置"格子的历史
胜率/收益定义。用 SQL 全量数据构建强弱字典，接入回测融合，看能否
提升胜率/夏普/收益率。

位置代理：近120日区间位置（只用当日之前数据，无未来函数）
强弱分：格子10日均收益 → 归一化 [0.4, 1.6]（强信号加权、弱信号降权）

模式：
  - plain  : 现状（形态融合 w=0.3，无强弱字典）
  - dict   : 现状 + 强弱字典加权（融合分数 × 强弱分）

用法：
    python tests/compare_pattern_dict.py --tickers 000063
    python tests/compare_pattern_dict.py --tickers 000063,600498 --start 2020-01-01 --end 2026-07-31
"""
import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sqlite3
import numpy as np
from collections import defaultdict

from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import TrendStrengthStrategy
from structure_engine.scanner.pattern_scanner import scan_patterns

DEFAULT_START, DEFAULT_END = "2020-01-01", "2026-07-31"
INITIAL_CASH = 500000
RANGE_LOOKBACK = 120


def build_strength_dict(db_path=None):
    """从 SQL 全量数据构建 形态×位置档 强弱字典
    位置代理：该股全期价格分位（数据驱动，无名称依赖）"""
    db = db_path or str(PROJECT_ROOT / "data" / "index_store" / "pattern_history.db")
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT symbol, pattern_name, match_price, return_10d
        FROM pattern_history 
        WHERE band_position_ready=1 AND return_10d IS NOT NULL AND match_price IS NOT NULL
    """).fetchall()
    conn.close()

    # 每只股票价格分位
    sym_prices = defaultdict(list)
    for sym, name, price, r10 in rows:
        sym_prices[sym].append(price)
    sym_arr = {s: np.array(v) for s, v in sym_prices.items()}

    def proxy_zone(sym, price):
        arr = sym_arr[sym]
        if len(arr) < 30:
            return 'mid'
        pct = (arr < price).mean()
        if pct < 0.2: return 'valley'
        if pct < 0.4: return 'rise_lower'
        if pct < 0.6: return 'rise_upper'
        if pct < 0.8: return 'peak'
        return 'fall_upper'

    cells = defaultdict(list)
    for sym, name, price, r10 in rows:
        cells[(name, proxy_zone(sym, price))].append(r10)

    # 归一化强弱分：格子均值 → [0.4, 1.6]
    cell_mean = {k: np.mean(v) for k, v in cells.items() if len(v) >= 20}
    if not cell_mean:
        return {}
    all_vals = np.array(list(cell_mean.values()))
    lo, hi = all_vals.min(), all_vals.max()
    strength = {}
    for k, m in cell_mean.items():
        if hi > lo:
            norm = (m - lo) / (hi - lo)  # 0~1
        else:
            norm = 0.5
        strength[k] = 0.4 + norm * 1.2  # 0.4~1.6
    return strength


def make_engine(strategy, mode, strength_dict, verbose=False):
    engine = BacktestPipeline(strategy, top_n=10, verbose=verbose)
    if mode == 'plain':
        return engine

    orig_fuse = engine._scan_and_fuse_patterns

    def fuse_with_dict(score_series, market_data, today):
        # 原融合
        score_series = orig_fuse(score_series, market_data, today)
        # 叠加强弱字典：对当日出现形态的股票，查字典强弱分加权
        for symbol in list(score_series.index):
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
                # 位置代理：近120日区间位置
                window = ohlc['close'].iloc[max(0, today_pos - RANGE_LOOKBACK):today_pos + 1]
                if len(window) < 30:
                    continue
                lo, hi = float(window.min()), float(window.max())
                if hi <= lo:
                    continue
                pos = (float(ohlc['close'].iloc[today_pos]) - lo) / (hi - lo)
                zone = ('valley' if pos < 0.2 else 'rise_lower' if pos < 0.4
                        else 'rise_upper' if pos < 0.6 else 'peak' if pos < 0.8 else 'fall_upper')
                # 当日形态的强弱分（取最强的）
                best = 1.0
                for r in results:
                    if r.get('date', '')[:10] == today_str:
                        name = r.get('pattern_type', '')
                        s = strength_dict.get((name, zone), 1.0)
                        best = max(best, s)  # 保守：只取正向强分
                if best != 1.0:
                    score_series[symbol] = score_series[symbol] * best
            except Exception:
                continue
        return score_series

    engine._scan_and_fuse_patterns = fuse_with_dict
    return engine


def run_one(tickers, start, end, mode, strength_dict):
    market_data = load_data(source='freestockdb', tickers=tickers,
                            start=start, end=end, frequency='1d', fq='qfq')
    if market_data is None or market_data.price is None or market_data.price.empty:
        print("❌ 数据加载失败，请检查 stockdb 服务 / 股票代码")
        sys.exit(1)
    strategy = TrendStrengthStrategy(short=5, long=20, verbose=False)
    t0 = time.perf_counter()
    engine = make_engine(strategy, mode, strength_dict)
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
    parser = argparse.ArgumentParser(description="形态×位置强弱字典回测实验")
    parser.add_argument("--tickers", default="000063")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--source", default="freestockdb")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    print(f"▶ 构建形态×位置强弱字典（SQL 全量）...")
    strength = build_strength_dict()
    print(f"  ✅ 字典格子数: {len(strength)}")

    print(f"▶ 对比: 现状 vs 强弱字典加权 | {tickers} | {args.start}~{args.end}")

    print("▶ 第 1 轮: 现状（形态融合 w=0.3）...")
    plain, t1 = run_one(tickers, args.start, args.end, 'plain', strength)
    print(f"  ✅ 完成 {t1:.1f}s 收益={plain['total_return']:.2%} 夏普={plain['sharpe']:.4f} 交易={plain['trades']}")

    print("▶ 第 2 轮: +强弱字典加权 ...")
    dct, t2 = run_one(tickers, args.start, args.end, 'dict', strength)
    print(f"  ✅ 完成 {t2:.1f}s 收益={dct['total_return']:.2%} 夏普={dct['sharpe']:.4f} 交易={dct['trades']}")

    lines = []
    lines.append("=" * 60)
    lines.append(f"形态×位置强弱字典回测（{tickers} | {args.start}~{args.end}）")
    lines.append(f"字典格子: {len(strength)}")
    lines.append("=" * 60)
    lines.append(f"{'指标':<14} {'现状':>12} {'+强弱字典':>14} {'差值':>12}")
    for k in ['total_return', 'sharpe', 'max_drawdown', 'trades']:
        a, b = plain[k], dct[k]
        lines.append(f"{k:<14} {a:>12.4f} {b:>14.4f} {b-a:>+12.4f}")
    lines.append("")
    verdict = []
    if dct['sharpe'] > plain['sharpe']: verdict.append("夏普↑")
    if dct['total_return'] > plain['total_return']: verdict.append("收益↑")
    if dct['max_drawdown'] >= plain['max_drawdown']: verdict.append("回撤改善")
    if not verdict: verdict = ["无提升"]
    lines.append(f"结论: {', '.join(verdict)}")
    out_path = PROJECT_ROOT / "outputs" / "pattern_dict_result.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding='utf-8')
    print("\n✅ 完成！完整对比已写入 outputs/pattern_dict_result.txt")
    print(f"   夏普: {plain['sharpe']:.4f} → {dct['sharpe']:.4f} | 收益: {plain['total_return']:.2%} → {dct['total_return']:.2%}")


if __name__ == "__main__":
    main()
