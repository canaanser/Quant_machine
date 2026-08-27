# -*- coding: utf-8 -*-
"""大盘因子细化验证：信号×大盘状态，按年份稳健性（2026-08-28）
第一次验证发现"反向过滤"（大盘向下时信号更强 53.9% vs 企稳 48.1%）。
本脚本按年份细分，确认"大盘向下组"优势是否稳健（非单年/熊市偶然）。
用法（Windows）：python scripts/verify_market_filter2.py
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
    ma20 = close.rolling(20).mean()
    state = {}
    for d, c in close.items():
        m = ma20.get(d)
        state[d.strftime('%Y-%m-%d')] = (1 if (m is not None and not np.isnan(m) and c >= m) else 0)

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

    base = [r for r in recs if ok(r)]
    up = [r for r in base if state.get(r[0], 0) == 1]
    down = [r for r in base if state.get(r[0], 0) == 0]
    print(f"信号总数 {len(base)} | 大盘向上 {len(up)} | 大盘向下 {len(down)}\n")


    def year_stat(name, lst):
        print(f"=== {name}（按年份）===")
        by = defaultdict(list)
        for r in lst:
            by[r[0][:4]].append(r[2])
        for y in sorted(by):
            a = np.array(by[y])
            print(f"  {y}: n={len(a):>5} 胜率={np.mean(a > 0):>6.1%} 5日均={np.mean(a):>+7.2%}")
        print()

    year_stat("大盘向下组（信号强化）", down)
    year_stat("大盘向上组（信号弱化）", up)

    # 汇总 2017+（排除起点年）
    for name, lst in (("大盘向下 2017+", [r for r in down if r[0] >= '2017-01-01']),
                      ("大盘向上 2017+", [r for r in up if r[0] >= '2017-01-01'])):
        if lst:
            a = np.array([r[2] for r in lst])
            print(f"{name}: n={len(a)} 胜率={np.mean(a > 0):.1%} 5日均={np.mean(a):+.2%}")


if __name__ == "__main__":
    main()
