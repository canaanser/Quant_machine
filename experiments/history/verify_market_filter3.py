# -*- coding: utf-8 -*-
"""大盘企稳升级版验证（2026-08-28）
MA20 方向太粗（向下组里急跌年 2008/2011 仍差），升级为"企稳判定"：
  企稳A = 当日收盘 > 前5日最低收盘（5日不创新低）
  企稳B = 当日收盘 > MA5（短期均线上方）
验证：深跌+缩量+反转信号 × 大盘企稳/未企稳 → 胜率对比 + 按年份稳健性。
用法（Windows）：python scripts/verify_market_filter3.py
"""
import sys, sqlite3
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "pybao"))


def main():
    from stock_sdk import get_bars

    bars = get_bars('000001.XSHG', count=3000, unit='1d')
    if isinstance(bars[0], dict):
        idx_df = pd.DataFrame(bars)
    else:
        cols = ['date', 'open', 'high', 'low', 'close']
        idx_df = pd.DataFrame([dict(zip(cols, b)) for b in bars])
    idx_df['date'] = pd.to_datetime(idx_df['date'].astype(str), errors='coerce')
    idx_df = idx_df.dropna(subset=['date']).set_index('date').sort_index()
    close = idx_df['close'].astype(float)

    low5_prev = close.rolling(5).min().shift(1)     # 前5日最低收盘
    ma5 = close.rolling(5).mean()
    stable_a = {}   # 5日不创新低
    stable_b = {}   # MA5上方
    for d, c in close.items():
        ds = d.strftime('%Y-%m-%d')
        l5 = low5_prev.get(d)
        m5 = ma5.get(d)
        stable_a[ds] = 1 if (l5 is not None and not np.isnan(l5) and c > l5) else 0
        stable_b[ds] = 1 if (m5 is not None and not np.isnan(m5) and c > m5) else 0

    conn = sqlite3.connect(f"file:{PROJECT / 'data/index_store/pattern_history.db'}?mode=ro", uri=True)
    atomic = {}
    for s, d, p, vs, br, sr in conn.execute(
            'SELECT symbol, date, pattern_id, volume_spike, body_ratio, shadow_ratio FROM atomic_features'):
        atomic[(s, p, d)] = (vs, br, sr)
    recs = []
    for s, p, dt, dd, r5 in conn.execute(
            'SELECT symbol, pattern_id, substr(match_date,1,10), drawdown_from_peak, return_5d '
            'FROM pattern_history WHERE return_5d IS NOT NULL'):
        a = atomic.get((s, p, dt))
        if a:
            recs.append((dt, dd, r5, a[0], a[1], a[2]))
    conn.close()

    def ok(r):
        dt, dd, r5, vs, br, sr = r
        return (dd is not None and dd < -0.20 and vs is not None and vs <= 0.1
                and br is not None and br >= 0.5 and sr is not None and sr <= 0.35)

    base = [r for r in recs if ok(r) and r[0] >= '2017-01-01']   # 2017+ 排除起点
    print(f"信号总数(2017+): {len(base)}\n")


    def stat(name, lst):
        if not lst:
            print(f'  {name:<22} 无样本')
            return
        a = np.array([r[2] for r in lst])
        print(f'  {name:<22} 样本={len(a):>6} 胜率={np.mean(a > 0):>6.1%} 5日均={np.mean(a):>+7.2%}')


    for key, name in ((stable_a, "企稳A(5日不创新低)"), (stable_b, "企稳B(MA5上方)")):
        up = [r for r in base if key.get(r[0], 0) == 1]
        down = [r for r in base if key.get(r[0], 0) == 0]
        print(f"=== 大盘{name} ===")
        stat("企稳组", up)
        stat("未企稳组", down)
        if up and down:
            a1 = np.mean(np.array([r[2] for r in up]) > 0)
            a2 = np.mean(np.array([r[2] for r in down]) > 0)
            print(f"  差: {a1-a2:+.1%}\n")

    # 企稳A 按年份稳健性
    print("=== 企稳A 按年份 ===")
    for label, lst in (("企稳组", [r for r in base if stable_a.get(r[0], 0) == 1]),
                       ("未企稳组", [r for r in base if stable_a.get(r[0], 0) == 0])):
        by = defaultdict(list)
        for r in lst:
            by[r[0][:4]].append(r[2])
        print(f"{label}:")
        for y in sorted(by):
            a = np.array(by[y])
            print(f"  {y}: n={len(a):>5} 胜率={np.mean(a > 0):>6.1%}")
        print()


if __name__ == "__main__":
    main()
