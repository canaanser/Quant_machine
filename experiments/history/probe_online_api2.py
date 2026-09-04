# -*- coding: utf-8 -*-
"""探测 v2：Query/Table 方法 + 试 1 次真实调用（2026-08-30）
只烧 1 次限额（get_fundamentals 试 1 次）——确认返回字段再批量
用法（Windows）：python -B scripts/probe_online_api2.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'pybao'))
import stock_sdk


def show_methods(name, obj, limit=25):
    ms = [x for x in dir(obj) if not x.startswith('_')]
    print(f"  {name} 方法/属性({len(ms)}): {ms[:limit]}")


def main():
    # 1. Query 对象方法（不耗限额）
    q = stock_sdk.query('finance')
    show_methods("query('finance')", q)
    # 2. TableNamespace finance
    show_methods("finance", stock_sdk.finance)
    # 3. Table balance / cash_flow
    show_methods("balance", stock_sdk.balance)
    show_methods("cash_flow", stock_sdk.cash_flow)
    # 4. QueryResult
    show_methods("QueryResult", stock_sdk.QueryResult, 15)
    # 5. 试 1 次真实调用（烧 1 次限额）：get_fundamentals(query('finance'))
    print("\n" + "=" * 56)
    print("🔬 试真实调用（消耗 1 次限额）")
    print("=" * 56)
    try:
        r = stock_sdk.get_fundamentals(q, date='2025-12-31')
        print(f"  get_fundamentals(query('finance'), date=2025-12-31):")
        print(f"    类型: {type(r)}")
        if hasattr(r, 'head'):
            print(f"    形状: {r.shape}  列: {list(r.columns)}")
            print(r.head(3).to_string())
        else:
            print(f"    {str(r)[:500]}")
    except Exception as e:
        print(f"  ❌ get_fundamentals: {e}")
        # 备选：balance.to_code
        try:
            r2 = stock_sdk.balance.to_code('000063')
            print(f"  balance.to_code('000063'): {str(r2)[:500]}")
        except Exception as e2:
            print(f"  ❌ balance.to_code: {e2}")


if __name__ == '__main__':
    main()
