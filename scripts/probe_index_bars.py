# -*- coding: utf-8 -*-
"""探测指数 K 线（get_bars + 聚宽风格代码，2026-08-28）
文档确认 stockdb 有指数，代码格式可能是 '000001.XSHG'(上证)/'000300.XSHG'(沪深300)/'399001.XSHE'(深成)
用法（Windows）：python scripts/probe_index_bars.py
"""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "pybao"))


def main():
    from stock_sdk import get_default_client
    client = get_default_client()

    candidates = [
        '000001.XSHG',    # 上证指数
        '000300.XSHG',    # 沪深300
        '000016.XSHG',    # 上证50
        '399001.XSHE',    # 深证成指
        '399006.XSHE',    # 创业板指
        '000001.XSHE',    # 平安银行（对照，应返回股价）
        '000300',         # 裸代码对照
    ]
    print("get_bars 探测（最近5根日K）：")
    for sec in candidates:
        try:
            bars = client.get_bars(sec, count=5, unit='1d')
            n = len(bars) if bars is not None else 0
            if n:
                last = bars[-1]
                # ndarray: date open high low close ... 取前几个
                print(f'  {sec:<14} {n} bars, 最新: {list(last)[:5]}')
            else:
                print(f'  {sec:<14} 0 bars')
        except Exception as e:
            print(f'  {sec:<14} 失败 {type(e).__name__}: {str(e)[:50]}')


if __name__ == "__main__":
    main()
