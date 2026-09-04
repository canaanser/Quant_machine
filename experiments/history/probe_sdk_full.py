# -*- coding: utf-8 -*-
"""SDK 接口全貌探测（2026-08-28 小二陈）
指南说 from stock_sdk import rd, bk, zb 且有 get_bars/get_price 等在线接口——
但 stock_sdk.py 里没找到，探测原生层/zb/bk/stockdb_sdk 的真实接口。
用法（Windows）：python scripts/probe_sdk_full.py
"""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "pybao"))


def show(name, obj):
    try:
        methods = [x for x in dir(obj) if not x.startswith('_')]
        print(f'  {name} ({len(methods)} 项): {methods[:40]}')
    except Exception as e:
        print(f'  {name}: 失败 {e}')


def main():
    import stock_sdk
    print('stock_sdk 模块:', stock_sdk.__file__)
    print('模块顶层导出:', [x for x in dir(stock_sdk) if not x.startswith('_')][:50])
    print()
    try:
        rd = stock_sdk.rd
        show('rd', rd)
    except Exception as e:
        print('rd 获取失败:', e)
    for mod in ('bk', 'zb', 'stockdb_sdk'):
        try:
            m = __import__(mod)
            print(f'\n=== {mod} 模块: {getattr(m, "__file__", "?")} ===')
            show(mod, m)
            if hasattr(m, 'get_bars'):
                print(f'  {mod} 有 get_bars!')
        except ImportError as e:
            print(f'\n{mod}: 不可导入 ({e})')
    # 在线接口直接试
    print()
    for api in ('get_bars', 'get_price', 'get_last_tick', 'get_fundamentals', 'query', 'get_ticks', 'cash_flow'):
        print(f'  stock_sdk.{api}: {"存在" if hasattr(stock_sdk, api) else "不存在"}')


if __name__ == "__main__":
    main()
