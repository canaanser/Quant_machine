# -*- coding: utf-8 -*-
"""
进场后一路跌 统计（2026-09-02 老板：鉴定退出机制）
=============================================================
两阶段：
  A. 训练期信号点（2021~2024-12-31 技术面信号）：信号后一路跌比率 → 鉴定信号质量
  B. 实测买入点（2025-01-01 空仓起步 multi门 实际买入）：买后一路跌 → 真实进场体验
"一路跌"量化口径（可调）：
  - 进场后 N 日内（默认 20 交易日）收盘从未回到进场价上方 = "进去就没回来"
  - 进场后最大浮亏（从进场价的下跌深度）
  - 进场后最低点出现时间（越晚=阴跌钝刀）
用法（Windows）：python -B scripts/stat_fall_after_entry.py
"""
import sys
import io
import json
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

TICKER_FILE = ROOT / 'data' / 'tickers' / 'tech300_seed99.txt'
TRAIN_DATE = '2024-12-31'
TEST_START = '2025-01-01'
START, END = '2021-01-01', '2026-08-27'
LOOK_DAYS = 20  # 进场后看多少日
FALL_DEF = 0.0   # 从未回到进场价上方 = "一路跌"（>0 可放宽为"涨不过X%"）


def main():
    import argparse as _argparse
    _ap = _argparse.ArgumentParser()
    _ap.add_argument("--a-only", action="store_true", help="只跑A段训练期信号统计(快)")
    _a_args = _ap.parse_args()
    import logging as _logging
    _logging.disable(_logging.CRITICAL)
    from core.data_loader import load_data
    from core.backtest import BacktestPipeline
    from core.strategy import SimpleStrategy

    codes = [l.strip().zfill(6) for l in open(TICKER_FILE) if l.strip()]
    names = json.load(open(ROOT / 'data' / 'stock_names.json', encoding='utf-8'))
    md = load_data(source='freestockdb', tickers=codes, start=START, end=END,
                   frequency='1d', fq='qfq')
    # 技术面合格票（同 tech300_oos）
    passed = []
    for code in codes:
        px = md.price[code].dropna()
        pxt = px[px.index <= pd.Timestamp(TRAIN_DATE)]
        if len(pxt) < 60:
            continue
        ret20 = pxt / pxt.shift(20) - 1
        sig = ret20[ret20 < -0.20]
        if code in md.volume.columns:
            vol = md.volume[code].dropna()
            vr = vol / vol.shift(1).rolling(20).mean()
            vv = vr.reindex(sig.index)
            sig = sig[vv > 0.7] if vv.notna().any() else sig
        if len(sig) >= 10:
            px10 = pxt.shift(-10)
            fwd = px10.reindex(sig.index).dropna()
            spx = pxt.reindex(fwd.index)
            wr = (fwd > spx).sum() / len(fwd) if len(fwd) else 0
            if wr >= 0.65:
                passed.append(code)
    print(f"技术面合格 {len(passed)} 只")

    # ===== A. 训练期信号点（2021~2024 信号触发日）=====
    print("\n" + "=" * 60)
    print("A. 训练期技术面信号 → 信号后走势")
    print("=" * 60)
    # 逐票收集信号点（各带自己的 px），统一统计
    px_map = {code: md.price[code].dropna() for code in passed}
    sig_entries = []
    for code in passed:
        px = px_map[code]
        pxt = px[px.index <= pd.Timestamp(TRAIN_DATE)]
        ret20 = pxt / pxt.shift(20) - 1
        sig = ret20[ret20 < -0.20]
        if code in md.volume.columns:
            vol = md.volume[code].dropna()
            vr = vol / vol.shift(1).rolling(20).mean()
            sig = sig[vr.reindex(sig.index) > 0.7] if vr.reindex(sig.index).notna().any() else sig
        for d in sig.index:
            sig_entries.append((code, d, float(pxt[d])))
    # 重新统计：分析每票信号后的走势
    a_rows = []
    for code, d, price in sig_entries:
        px = px_map[code]
        after = px[px.index > d]
        if len(after) < LOOK_DAYS:
            continue
        window = after.iloc[:LOOK_DAYS]
        a_rows.append({'code': code, '进场日': d, '价格': price,
                       '最大涨': (window / price - 1).max(),
                       '最大跌': (window / price - 1).min(),
                       '回过': bool((window > price).any()),
                       '到低天数': (window.idxmin() - d).days})
    if a_rows:
        adf = pd.DataFrame(a_rows)
        n = len(adf)
        nb = adf[~adf['回过']]
        df10 = adf[adf['最大跌'] < -0.10]
        print(f"训练期信号 {n} 次")
        print(f"  信号后{LOOK_DAYS}日从未回到信号价上方(一路跌): {len(nb)}/{n} = {len(nb)/n:.0%}")
        print(f"  最深跌超10%: {len(df10)}/{n} = {len(df10)/n:.0%}")
        print(f"  平均最大跌 {adf['最大跌'].mean():.1%} | 平均最大涨 {adf['最大涨'].mean():.1%}")
        if len(nb):
            print("  最惨5次信号:")
            for _, r in nb.nsmallest(min(5, len(nb)), '最大跌').iterrows():
                print(f"    {r['进场日'].date()} {r['code']} {names.get(r['code'],'?')} 信号价{r['价格']:.2f} "
                      f"最大跌{r['最大跌']:.1%} 到低{r['到低天数']}天")
    else:
        print("信号样本不足")

    if _a_args.a_only:
        print("\n（--a-only：跳过B段）")
        return
    # ===== B. 实测买入点（2025 空仓起步 multi门 实际买入）=====
    print("\n" + "=" * 60)
    print("B. 2025实测 实际买入点 → 买后走势")
    print("=" * 60)
    sub = load_data(source='freestockdb', tickers=passed, start=START, end=END,
                    frequency='1d', fq='qfq')
    st = SimpleStrategy(5, 20)
    eng = BacktestPipeline(st, top_n=10, risk_config={}, verbose=False,
                           stop_loss_pct=None, take_profit_pct=0.30, trend_gate='multi')
    eng.trend_gate_threshold = 2
    with contextlib.redirect_stdout(io.StringIO()):
        eng.run(sub, initial_cash=500000, auto_save=False, trade_start=TEST_START)
    df_tr = eng.trades.copy()
    df_tr['Date'] = pd.to_datetime(df_tr['Date'])
    buys = df_tr[df_tr['Action'] == 'BUY']
    buys25 = buys[buys['Date'] >= pd.Timestamp(TEST_START)]
    print(f"2025 起实际买入 {len(buys25)} 笔")
    b_entries = [(r['Date'], float(r['Price'])) for _, r in buys25.iterrows()]
    # 每票单独取价格序列（buy 分布在多票）
    # 聚合：需要每票的 px → 按票分组
    per_stock = {}
    for code in passed:
        per_stock[code] = sub.price[code].dropna()
    res = []
    for _, r in buys25.iterrows():
        code = r['Stock']
        px = per_stock.get(code)
        if px is None:
            continue
        d, price = r['Date'], float(r['Price'])
        after = px[px.index > d]
        if len(after) < LOOK_DAYS:
            continue
        window = after.iloc[:LOOK_DAYS]
        res.append({'code': code, 'name': names.get(code, '?'),
                    '进场日': d, '价格': price,
                    '最大涨': (window / price - 1).max(),
                    '最大跌': (window / price - 1).min(),
                    '回过': bool((window > price).any()),
                    '到低天数': (window.idxmin() - d).days})
    if res:
        rdf = pd.DataFrame(res)
        n = len(rdf)
        nb = rdf[~rdf['回过']]
        df10 = rdf[rdf['最大跌'] < -0.10]
        print(f"进场后{LOOK_DAYS}日从未回本(一路跌): {len(nb)}/{n} = {len(nb)/n:.0%}")
        print(f"最深跌超10%: {len(df10)}/{n} = {len(df10)/n:.0%}")
        print(f"平均最大跌 {rdf['最大跌'].mean():.1%} | 平均最大涨 {rdf['最大涨'].mean():.1%}")
        print("最惨5次:")
        for _, r in nb.nsmallest(min(5, len(nb)), '最大跌').iterrows():
            print(f"  {r['进场日'].date()} {r['code']} {r['name']} 买{r['价格']:.2f} 最大跌{r['最大跌']:.1%} 到低{r['到低天数']}天")


if __name__ == '__main__':
    main()
