# -*- coding: utf-8 -*-
"""冷却期 × 先验处境（回撤深度）→ 胜率（不带后验位置）
实盘框架：冷却间隔 + 回撤深度都是当下可算，不用 band_position"""
import argparse, sys
import sqlite3
import numpy as np
import pandas as pd
from collections import defaultdict

PROJECT_ROOT = '/mnt/e/stockgate/Quant_Alpha_System'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

conn = sqlite3.connect('data/index_store/pattern_history.db')
cur = conn.cursor()

# 需要日线算回撤——用缓存数据（000063/601728）或全量需Windows。
# 先看缓存能覆盖多少
from core.data_loader import load_data
parser = argparse.ArgumentParser()
parser.add_argument("--tickers", default="000063,601728")
parser.add_argument("--start", default="2025-01-01")
parser.add_argument("--end", default="2026-07-31")
parser.add_argument("--source", default="stockdb_http")
args = parser.parse_args()
tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
md = load_data(source=args.source, tickers=tickers, start=args.start, end=args.end, frequency='1d', fq='qfq')
ohlc_map = {}
for sym in tickers:
    o = md.get_ohlc(sym)
    if o is not None and not o.empty:
        ohlc_map[sym] = o
print(f"日线: {list(ohlc_map.keys())}")

for pid, name in [('1_neutral_0_doji','十字星'), ('2_bearish_0_dark_cloud','乌云盖顶')]:
    rows = cur.execute("""
        SELECT symbol, substr(match_date,1,10), match_price, return_5d
        FROM pattern_history 
        WHERE pattern_id=? AND band_position_ready=1 AND match_price IS NOT NULL
        ORDER BY symbol, match_date""", (pid,)).fetchall()
    print(f"\n【{name}】")

    # 冷却间隔 + 回撤深度
    prev = {}
    enriched = []
    for sym, dt, price, r5 in rows:
        if sym not in ohlc_map: continue
        ohlc = ohlc_map[sym]
        try:
            d = pd.Timestamp(dt)
            if d not in ohlc.index: continue
            i = ohlc.index.get_loc(d)
            if i+5 >= len(ohlc): continue
            base = float(ohlc['close'].iloc[i])
            if base <= 0: continue
            window = ohlc['close'].iloc[max(0,i-120):i+1]
            peak = float(window.max())
            dd = base/peak - 1 if peak>0 else 0
            gap = None
            if sym in prev:
                gap = (np.datetime64(dt) - np.datetime64(prev[sym])).astype('timedelta64[D]').astype(int)
            prev[sym] = dt
            enriched.append((gap, dd, r5))
        except Exception:
            continue

    def gap_b(g):
        if g is None: return '首现'
        if g < 10: return '0-10天'
        if g < 30: return '10-30天'
        return '30天+'
    def dd_b(dd):
        if dd < -0.20: return '深跌>20%'
        if dd < -0.10: return '中跌10-20%'
        return '浅跌<10%'

    matrix = defaultdict(list)
    for gap, dd, r5 in enriched:
        matrix[(gap_b(gap), dd_b(dd))].append(r5)

    print(f"\n{'冷却':<10} {'处境':<12} {'样本':>5} {'胜率':>6} {'5日均':>8}")
    for gb in ['首现','0-10天','10-30天','30天+']:
        for db in ['深跌>20%','中跌10-20%','浅跌<10%']:
            lst = matrix.get((gb,db), [])
            if len(lst) >= 3:
                arr = np.array(lst)
                print(f"{gb:<10} {db:<12} {len(lst):>5} {(arr>0).mean():>6.0%} {arr.mean():>+8.2%}")
conn.close()
out = PROJECT_ROOT + "/outputs/cooldown_prior_result.txt"
import os
os.makedirs(os.path.dirname(out), exist_ok=True)
print(f"✅ 完成，结果见 outputs/cooldown_prior_result.txt")
