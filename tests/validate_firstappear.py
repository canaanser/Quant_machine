# -*- coding: utf-8 -*-
"""
首现/长期冷却 × 处境 深化验证（聚焦乌云盖顶反弹信号）
==============================================
上轮发现：乌云盖顶 首现×中跌(10-20%) = 67%胜率 +8.27%（但 n=6 太小）
本脚本：
1. 把"首现"放宽为"距上次出现 ≥30/60/90 天"（长期冷却），样本量增大
2. 中跌处境细分（10-15% / 15-20%）
3. 看 D+1~D+5 逐日收益结构（反弹集中在哪天）
4. 分股票看普遍性
5. 十字星作对照
用法：python tests/validate_firstappear.py --tickers "..." --start 2020-01-01 --end 2026-07-31
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sqlite3
import numpy as np
import pandas as pd
from collections import defaultdict

from core.data_loader import load_data

LOOKBACK = 120


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", default="000063,601728")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-07-31")
    parser.add_argument("--source", default="stockdb_http")
    args = parser.parse_args()
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    conn = sqlite3.connect(str(PROJECT_ROOT / "data" / "index_store" / "pattern_history.db"))
    cur = conn.cursor()
    recs = cur.execute("""
        SELECT symbol, substr(match_date,1,10), match_price, pattern_name
        FROM pattern_history WHERE band_position_ready=1 AND match_price IS NOT NULL
        ORDER BY symbol, match_date
    """).fetchall()
    conn.close()
    print(f"✅ pattern_history: {len(recs)} 条")

    md = load_data(source=args.source, tickers=tickers, start=args.start, end=args.end,
                   frequency='1d', fq='qfq')
    print(f"✅ 日线: {len(md.price.columns)} 只, {len(md.price)} 交易日")

    ohlc_map = {}
    for sym in set(r[0] for r in recs):
        try:
            o = md.get_ohlc(sym)
            if o is not None and not o.empty:
                ohlc_map[sym] = o
        except Exception:
            continue

    # 收集: (形态类, 冷却天数, 回撤, 逐日收益[1..5], symbol)
    prev = {}
    samples = []
    for sym, mdate, mprice, pname in recs:
        if sym not in ohlc_map:
            continue
        ohlc = ohlc_map[sym]
        try:
            dt = pd.Timestamp(mdate)
            if dt not in ohlc.index:
                continue
            i = ohlc.index.get_loc(dt)
            if i + 5 >= len(ohlc) or i < 30:
                continue
            base = float(ohlc['close'].iloc[i])
            if base <= 0:
                continue
            window = ohlc['close'].iloc[max(0, i - LOOKBACK):i + 1]
            peak = float(window.max())
            dd = base / peak - 1 if peak > 0 else 0.0
            # 冷却天数
            gap = None
            if sym in prev:
                gap = (dt - prev[sym]).days
            prev[sym] = dt
            if '乌云' in pname:
                pat = '乌云盖顶'
            elif '十字星' in pname:
                pat = '十字星'
            else:
                pat = '其他'
            daily = [float(ohlc['close'].iloc[i+j]) / base - 1 for j in range(1, 6)]
            samples.append({'pat': pat, 'gap': gap, 'dd': dd, 'd': daily, 'sym': sym})
        except Exception:
            continue
    print(f"✅ 样本: {len(samples)}")

    def fmt(daily):
        return " ".join(f"D{j+1}={daily[j]:+.2%}" for j in range(5))

    lines = []
    lines.append("=" * 84)
    lines.append("长期冷却 × 处境 深化验证（聚焦乌云盖顶反弹信号）")
    lines.append("冷却=距上次出现天数 | 回撤=近120日高点回撤 | 无未来函数")
    lines.append("=" * 84)

    # 1. 乌云盖顶：冷却阈值 × 中跌处境
    lines.append("\n【1. 乌云盖顶 · 冷却阈值 × 中跌(10-20%)处境】")
    lines.append(f"{'冷却定义':<18} {'样本':>5} {'胜率':>6} {'5日累计':>9} {'D+1~D+5':>40}")
    for label, thr in [('首现(从无)', 10**9), ('冷却≥60天', 60), ('冷却≥90天', 90), ('冷却≥30天', 30)]:
        lst = [s for s in samples if s['pat'] == '乌云盖顶' and -0.20 < s['dd'] <= -0.10
               and (s['gap'] is None or s['gap'] >= thr)]
        if len(lst) < 3:
            continue
        arr = np.array([s['d'] for s in lst])
        cum5 = arr.sum(axis=1)
        lines.append(f"{label:<18} {len(lst):>5} {(cum5>0).mean():>6.0%} {cum5.mean():>+9.2%} {fmt(arr.mean(axis=0))}")

    # 2. 乌云盖顶 冷却≥60天：回撤细分
    lines.append("\n【2. 乌云盖顶 · 冷却≥60天 × 回撤细分】")
    lines.append(f"{'回撤档':<14} {'样本':>5} {'胜率':>6} {'5日累计':>9} {'D+1~D+5':>40}")
    for label, lo, hi in [('浅跌<10%', 0, -0.10), ('中跌10-15%', -0.15, -0.10),
                          ('中跌15-20%', -0.20, -0.15), ('深跌20-30%', -0.30, -0.20),
                          ('深跌>30%', -1.0, -0.30)]:
        lst = [s for s in samples if s['pat'] == '乌云盖顶'
               and (s['gap'] is None or s['gap'] >= 60)
               and lo <= s['dd'] < hi]
        if len(lst) < 3:
            continue
        arr = np.array([s['d'] for s in lst])
        cum5 = arr.sum(axis=1)
        lines.append(f"{label:<14} {len(lst):>5} {(cum5>0).mean():>6.0%} {cum5.mean():>+9.2%} {fmt(arr.mean(axis=0))}")

    # 3. 最强组合分股票
    lines.append("\n【3. 乌云盖顶 · 冷却≥60天 × 中跌(10-20%) · 分股票】")
    best = [s for s in samples if s['pat'] == '乌云盖顶'
            and (s['gap'] is None or s['gap'] >= 60) and -0.20 < s['dd'] <= -0.10]
    by_sym = defaultdict(list)
    for s in best:
        by_sym[s['sym']].append(s)
    pos = neg = 0
    for sym in sorted(by_sym):
        lst = by_sym[sym]
        arr = np.array([s['d'] for s in lst])
        cum5 = arr.sum(axis=1).mean()
        if cum5 > 0: pos += 1
        else: neg += 1
        lines.append(f"  {sym}: n={len(lst):>2} 5日累计={cum5:+.2%}")
    lines.append(f"  → 5日累计>0: {pos}只, <0: {neg}只")

    # 4. 十字星对照
    lines.append("\n【4. 对照：十字星 · 冷却≥60天 × 中跌】")
    dc = [s for s in samples if s['pat'] == '十字星'
          and (s['gap'] is None or s['gap'] >= 60) and -0.20 < s['dd'] <= -0.10]
    if len(dc) >= 3:
        arr = np.array([s['d'] for s in dc])
        cum5 = arr.sum(axis=1)
        lines.append(f"  十字星: n={len(dc)} 胜率={(cum5>0).mean():.0%} 5日累计={cum5.mean():+.2%} {fmt(arr.mean(axis=0))}")

    out = PROJECT_ROOT / "outputs" / "firstappear_result.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding='utf-8')
    print("\n✅ 完成！结果见 outputs/firstappear_result.txt")


if __name__ == "__main__":
    main()
