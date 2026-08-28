# -*- coding: utf-8 -*-
"""
数据空洞检测与修复（2026-08-29 小二陈）
================================================================
老板要求：空洞/假数据标好 + 缓存原因补上。
检测：每只票在交易日历上的价格缺失（NaN/空洞）——区分：
  - 连续空洞（≥3天连续缺失）= 疑似停牌（正常，A股停牌）
  - 零星空洞（<3天或隔断）= 疑似数据问题（拉取/stockdb缺失）→ 尝试补拉验证
补拉：对疑似空洞日期，rd.get_data 单区间重拉——stockdb 有数据则输出"可补"，
      没有则标注"stockdb 本身缺"。

用法（Windows，python -B）：
    python -B scripts/check_data_gaps.py                     # 84只 全区间
    python -B scripts/check_data_gaps.py --tickers 000657,000063
"""
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / 'pybao') not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / 'pybao'))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import pandas as pd
import numpy as np
from core.data_loader import load_data
import config.config as config_mod


def load_names() -> dict:
    p = PROJECT_ROOT / 'data' / 'stock_names.json'
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return {}


def find_gaps(series: pd.Series, trade_days) -> list:
    """找该票在交易日历上的缺失段（空洞）——返回 [(起始, 结束, 天数)]"""
    present = set(series.dropna().index)
    gaps = []
    start = None
    prev = None
    for d in trade_days:
        if d not in present:
            if start is None:
                start = d
            prev = d
        else:
            if start is not None:
                gaps.append((start, prev, (prev - start).days + 1))
                start = None
    if start is not None:
        gaps.append((start, prev, (prev - start).days + 1))
    return gaps


def main():
    import argparse
    import logging
    parser = argparse.ArgumentParser(description="数据空洞检测与修复")
    parser.add_argument("--tickers", default=",".join(config_mod.SCAN_TICKERS))
    parser.add_argument("--start", default='2017-01-01')
    parser.add_argument("--end", default='2026-08-27')
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    names = load_names()
    print(f"🚀 检测 {len(tickers)} 只数据空洞：{args.start} ~ {args.end} ...")
    md = load_data(source='freestockdb', tickers=tickers,
                   start=args.start, end=args.end, frequency='1d', fq='qfq')
    trade_days = list(md.price.index)
    print(f"✅ 交易日历 {len(trade_days)} 天，检测中...\n")

    all_gaps = []
    for code in tickers:
        if code not in md.price.columns:
            print(f"⚠️ {code} 无任何数据（stockdb 缺失或代码错误）")
            continue
        series = md.price[code]
        gaps = find_gaps(series, trade_days)
        for (g0, g1, n) in gaps:
            kind = "疑似停牌" if n >= 3 else "疑似数据空洞"
            all_gaps.append((code, names.get(code, '?'), g0, g1, n, kind))

    if not all_gaps:
        print("✅ 无空洞——数据完整")
        return

    # 汇总输出
    print("=" * 78)
    print(f"📊 数据空洞报告（共 {len(all_gaps)} 段，{len(set(g[0] for g in all_gaps))} 只票）")
    print("=" * 78)
    suspicious = [g for g in all_gaps if g[5] == "疑似数据空洞"]
    suspended = [g for g in all_gaps if g[5] == "疑似停牌"]
    print(f"🔴 疑似数据空洞（零星缺失，<3天）：{len(suspicious)} 段 —— 需补拉验证")
    print(f"🟡 疑似停牌（连续≥3天）：{len(suspended)} 段 —— 正常，无需补")
    print("-" * 78)
    for (code, nm, g0, g1, n, kind) in suspicious[:50]:
        print(f"  🔴 {code} {nm}: {str(g0)[:10]} ~ {str(g1)[:10]}（{n}天）")
    if len(suspicious) > 50:
        print(f"  ... 等共 {len(suspicious)} 段")
    print("-" * 78)
    for (code, nm, g0, g1, n, kind) in suspended[:15]:
        print(f"  🟡 {code} {nm}: {str(g0)[:10]} ~ {str(g1)[:10]}（{n}天）")
    if len(suspended) > 15:
        print(f"  ... 等共 {len(suspended)} 段")

    # 对疑似空洞补拉验证（stockdb 有没有数据）
    if suspicious:
        print("\n🔍 补拉验证（看 stockdb 是否有这些空洞的数据）...")
        from stock_sdk import rd, init
        init(host="127.0.0.1", port=7899)
        fixable, missing = 0, 0
        for (code, nm, g0, g1, n, kind) in suspicious:
            try:
                r = rd.get_data(code=code, start=str(g0).replace('-', ''),
                                end=str(g1).replace('-', ''), frequency='1d',
                                fq='qfq', fields="date,code,close", as_df=True)
                if r is not None and not r.empty:
                    fixable += 1
                    print(f"  ✅ {code} {nm} {str(g0)[:10]}~{str(g1)[:10]}: stockdb 有 {len(r)} 天数据——可补")
                else:
                    missing += 1
                    print(f"  ❌ {code} {nm} {str(g0)[:10]}~{str(g1)[:10]}: stockdb 也缺——数据源问题")
            except Exception as e:
                missing += 1
                print(f"  ⚠️ {code}: {str(e)[:60]}")
        print(f"\n📋 结论：可补 {fixable} 段（缓存/拉取原因，可修复）/ stockdb 缺 {missing} 段（数据源问题）")


if __name__ == "__main__":
    main()
