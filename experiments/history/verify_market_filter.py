# -*- coding: utf-8 -*-
"""大盘因子验证：深跌+缩量+反转信号 × 上证指数 MA20 状态（2026-08-28）
验证"信号 + 大盘企稳过滤"是否提升胜率：
  对每个信号日期，查上证指数（000001.XSHG）当日 MA20 方向：
  - 大盘 MA20 向上（企稳）组 vs 向下组 → 胜率对比
用法（Windows，SDK 已更新）：python scripts/verify_market_filter.py
"""
import sys, sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "pybao"))

MA_WINDOW = 20


def main():
    from stock_sdk import get_bars

    # 1. 拉上证指数日K（2016 起，约 2600 根；在线接口限制则分批/降级）
    print("拉取上证指数日K...")
    bars = None
    for cnt in (3000, 1500, 800):
        try:
            bars = get_bars('000001.XSHG', count=cnt, unit='1d')
            if bars is not None and len(bars) > 100:
                print(f"  成功拉取 {len(bars)} 根")
                break
        except Exception as e:
            print(f"  count={cnt} 失败: {str(e)[:50]}")
    if bars is None or len(bars) < 100:
        print("❌ 指数数据拉取失败")
        return

    # 2. 构建上证指数 DataFrame（date/close）
    if isinstance(bars[0], dict):
        idx_df = pd.DataFrame(bars)
    else:
        cols = ['date', 'open', 'high', 'low', 'close']
        idx_df = pd.DataFrame([dict(zip(cols, b)) for b in bars])
    idx_df['date'] = pd.to_datetime(idx_df['date'].astype(str), errors='coerce')
    idx_df = idx_df.dropna(subset=['date']).set_index('date').sort_index()
    close = idx_df['close'].astype(float)
    ma20 = close.rolling(MA_WINDOW).mean()
    state = {}   # date_str -> 1(MA20向上) / 0(向下)
    prev = None
    for d, c in close.items():
        m = ma20.get(d)
        if m is None or np.isnan(m):
            state[d.strftime('%Y-%m-%d')] = 0
            continue
        state[d.strftime('%Y-%m-%d')] = 1 if c >= m else 0
    print(f"上证指数: {close.index.min().date()} ~ {close.index.max().date()}, {len(close)} 根")

    # 3. 读信号（深跌+缩量+反转，4条件）
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
    print(f"信号总数: {len(base)}")

    # 4. 按大盘状态分组
    up = [r for r in base if state.get(r[0], 0) == 1]
    down = [r for r in base if state.get(r[0], 0) == 0]
    unknown = [r for r in base if r[0] not in state]

    def stat(name, lst):
        if not lst:
            print(f'  {name:<18} 无样本')
            return
        a = np.array([r[2] for r in lst])
        print(f'  {name:<18} 样本={len(a):>6} 胜率={np.mean(a > 0):>6.1%} 5日均={np.mean(a):>+7.2%}')

    print()
    print("=== 深跌+缩量+反转 × 上证MA20 ===")
    stat("全部信号", base)
    stat("大盘MA20向上(企稳)", up)
    stat("大盘MA20向下", down)
    if unknown:
        print(f"  （{len(unknown)} 个信号无指数日期匹配）")
    if up and down:
        a1 = np.mean(np.array([r[2] for r in up]) > 0)
        a2 = np.mean(np.array([r[2] for r in down]) > 0)
        print(f"\n结论：企稳组 {a1:.1%} vs 向下组 {a2:.1%}，差 {a1-a2:+.1%}")


if __name__ == "__main__":
    main()
