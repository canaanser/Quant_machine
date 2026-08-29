# -*- coding: utf-8 -*-
"""探测 v4：纯只读（2026-08-30）——绝不调用任何执行方法
只 dir() + 读非 callable 属性值——看 query 对象暴露的服务端表达式/url——零消耗 100%
用法（Windows）：python -B scripts/probe_online_api4.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'pybao'))
import stock_sdk


def dump_attrs(label, obj):
    """只读属性（非 callable），绝不调用"""
    print(f"\n=== {label} (type={type(obj)}) ===")
    for attr in dir(obj):
        if attr.startswith('_'):
            continue
        try:
            v = getattr(obj, attr)
            if callable(v):
                print(f"  {attr}: <callable>")
            else:
                print(f"  {attr} = {v}")
        except Exception as e:
            print(f"  {attr}: 读取异常 {str(e)[:50]}")


def main():
    # 1. query 对象 + filter 后
    dump_attrs("query('finance')", stock_sdk.query('finance'))
    dump_attrs("query('finance').filter('000063')", stock_sdk.query('finance').filter('000063'))
    # 2. balance/cash_flow Table
    dump_attrs("balance", stock_sdk.balance)
    dump_attrs("cash_flow", stock_sdk.cash_flow)
    # 3. finance TableNamespace
    dump_attrs("finance", stock_sdk.finance)
    # 4. QueryResult 类属性
    dump_attrs("QueryResult", stock_sdk.QueryResult)
    # 5. get_fundamentals 的 docstring（可能含示例）
    print("\n=== get_fundamentals.__doc__ ===")
    print((stock_sdk.get_fundamentals.__doc__ or '无')[:800])


if __name__ == '__main__':
    main()
