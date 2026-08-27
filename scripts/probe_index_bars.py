# -*- coding: utf-8 -*-
"""指数通道探测 v2（模块级接口，2026-08-28）
接口在 stock_sdk 模块顶层（get_bars/get_all_securities 等），不是 StockDBClient 类方法。
用法（Windows）：python scripts/probe_index_bars.py
"""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "pybao"))


def main():
    from stock_sdk import get_bars, get_all_securities

    print("=== 1. get_all_securities（证券清单，找指数）===")
    try:
        secs = get_all_securities()
        print("返回类型:", type(secs))
        if hasattr(secs, 'head'):
            print(secs.head(20))
        elif isinstance(secs, dict):
            ks = list(secs.keys())[:20]
            print("keys 样例:", ks)
        else:
            print(str(secs)[:500])
    except Exception as e:
        print(f"失败 {type(e).__name__}: {e}")

    print("\n=== 2. get_bars 指数 K 线（模块级）===")
    for sec in ['000001.XSHG', '000300.XSHG', '399001.XSHE', '399006.XSHE', '000001.XSHE']:
        try:
            bars = get_bars(sec, count=5, unit='1d')
            n = len(bars) if bars is not None else 0
            if n:
                last = bars[-1]
                print(f'  {sec:<14} {n} bars, 最新: {list(last)[:6]}')
            else:
                print(f'  {sec:<14} 0 bars')
        except Exception as e:
            print(f'  {sec:<14} 失败 {type(e).__name__}: {str(e)[:60]}')


if __name__ == "__main__":
    main()
