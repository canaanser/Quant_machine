# -*- coding: utf-8 -*-
"""
乌云盖顶 @ 深回撤处境 · 深化验证
==============================================
上一轮发现：乌云盖顶在深回撤(>20%)下 D+5 = -0.77%（基准 deep +1.04%），
是唯一有独立方向信号的处境×形态组合。本脚本深化验证其稳健性：

1. 回撤深度细分档（20-30/30-40/40%+）→ 看信号是否随深度单调增强
2. 分股票 → 看信号是否普遍（还是几只票带动）
3. 下跌持续天数 → 看"跌得久"是否增强信号
4. 与全形态基准、十字星对照

用法：python tests/validate_darkcloud_deep.py --tickers "..." --start 2020-01-01 --end 2026-07-31
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
    parser = argparse.ArgumentParser(description="乌云盖顶@深回撤深化验证")
    parser.add_argument("--tickers", default="000063")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-07-31")
    parser.add_argument("--source", default="freestockdb")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    conn = sqlite3.connect(str(PROJECT_ROOT / "data" / "index_store" / "pattern_history.db"))
    cur = conn.cursor()
    recs = cur.execute("""
        SELECT symbol, substr(match_date,1,10), match_price, pattern_name
        FROM pattern_history WHERE band_position_ready=1 AND match_price IS NOT NULL
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

    # 收集所有样本: (形态类, 回撤细分档, symbol, 下跌天数, [d1..d5])
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
            if i + 5 >= len(ohlc) or i < LOOKBACK:
                continue
            base = float(ohlc['close'].iloc[i])
            if base <= 0:
                continue
            window = ohlc['close'].iloc[max(0, i - LOOKBACK):i + 1]
            peak = float(window.max())
            drawdown = base / peak - 1 if peak > 0 else 0.0
            # 下跌天数 = 当前日 - 窗口内峰值日
            peak_global = window.idxmax()
            days_since_peak = (dt - peak_global).days
            if '乌云' in pname:
                pat = '乌云盖顶'
            elif '十字星' in pname:
                pat = '十字星'
            else:
                pat = '其他'
            daily = [float(ohlc['close'].iloc[i+j]) / base - 1 for j in range(1, 6)]
            samples.append({
                'pat': pat, 'dd': drawdown, 'sym': sym,
                'days': days_since_peak, 'd': daily,
            })
        except Exception:
            continue
    print(f"✅ 样本: {len(samples)} 条")

    def wmean(lst):
        ws = np.array([1.0 + abs(s['dd']) / 0.10 for s in lst])
        arr = np.array([s['d'] for s in lst])
        return np.average(arr, axis=0, weights=ws), len(lst)

    lines = []
    lines.append("=" * 80)
    lines.append("乌云盖顶 @ 深回撤 · 深化验证")
    lines.append(f"样本: {len(samples)} | 无未来函数（回撤/天数均截至当日可算）")
    lines.append("=" * 80)

    # 1. 回撤细分档
    lines.append("\n【1. 回撤深度细分档】（加权 D+1/D+3/D+5）")
    lines.append(f"{'形态':<8} {'回撤档':<14} {'样本':>6} {'D+1':>8} {'D+3':>8} {'D+5':>8} {'D+1胜率':>8}")
    bands = [('10-20%', -0.20, -0.10), ('20-30%', -0.30, -0.20),
             ('30-40%', -0.40, -0.30), ('40%+', -1.0, -0.40)]
    for pat in ['乌云盖顶', '十字星', '其他']:
        for label, lo, hi in bands:
            lst = [s for s in samples if s['pat'] == pat and lo < s['dd'] <= hi]
            if len(lst) < 10:
                continue
            w, n = wmean(lst)
            lines.append(f"{pat:<8} {label:<14} {n:>6} {w[0]:>8.2%} {w[2]:>8.2%} {w[4]:>8.2%} "
                         f"{(np.array([s['d'][0] for s in lst])>0).mean():>8.0%}")

    # 2. 分股票（深回撤>20% 的乌云盖顶）
    lines.append("\n【2. 乌云盖顶 @ 深回撤(>20%) 分股票】")
    dc_deep = [s for s in samples if s['pat'] == '乌云盖顶' and s['dd'] < -0.20]
    by_sym = defaultdict(list)
    for s in dc_deep:
        by_sym[s['sym']].append(s)
    neg = pos = 0
    for sym in sorted(by_sym):
        lst = by_sym[sym]
        if len(lst) < 3:
            continue
        arr = np.array([s['d'] for s in lst])
        d5 = arr[:, 4].mean()
        if d5 < 0:
            neg += 1
        else:
            pos += 1
        lines.append(f"  {sym}: n={len(lst):>3} D+5={d5:+.2%}")
    lines.append(f"  → D+5<0 股票: {neg} 只, >0: {pos} 只")

    # 3. 下跌天数维度
    lines.append("\n【3. 乌云盖顶@深回撤 × 下跌持续天数】")
    lines.append(f"{'下跌天数':<12} {'样本':>6} {'D+1':>8} {'D+5':>8} {'D+1胜率':>8}")
    for label, lo, hi in [('<30天', 0, 30), ('30-60天', 30, 60), ('60-120天', 60, 120), ('>120天', 120, 99999)]:
        lst = [s for s in dc_deep if lo <= s['days'] < hi]
        if len(lst) < 10:
            continue
        w, n = wmean(lst)
        lines.append(f"{label:<12} {n:>6} {w[0]:>8.2%} {w[4]:>8.2%} "
                     f"{(np.array([s['d'][0] for s in lst])>0).mean():>8.0%}")

    out_path = PROJECT_ROOT / "outputs" / "darkcloud_deep_result.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding='utf-8')
    print("\n✅ 完成！结果写入 outputs/darkcloud_deep_result.txt")


if __name__ == "__main__":
    main()
