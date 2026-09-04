# -*- coding: utf-8 -*-
"""探测 stock_sdk 在线财务接口的正确用法（2026-08-30）
老板："看还有更多可用的吗"——finance/balance/cash_flow/get_fundamentals/query/get_all_securities
只读探测：inspect 签名/文档/属性，不消耗限额
用法（Windows）：python -B scripts/probe_online_api.py
"""
import sys
import inspect
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'pybao'))
import stock_sdk


def show(name):
    obj = getattr(stock_sdk, name, None)
    if obj is None:
        print(f"❌ {name}: 不存在")
        return
    print(f"\n{'='*56}\n📦 {name}: {type(obj)}\n{'='*56}")
    if callable(obj):
        try:
            print(f"  签名: {inspect.signature(obj)}")
        except Exception:
            pass
        doc = (obj.__doc__ or '').strip()[:400]
        if doc:
            print(f"  文档: {doc}")
    attrs = [x for x in dir(obj) if not x.startswith('_')]
    if attrs and not callable(obj):
        print(f"  属性/方法: {attrs[:20]}")


def main():
    print("stock_sdk 文件:", stock_sdk.__file__)
    for name in ('get_fundamentals', 'get_bars', 'get_price', 'get_security_info',
                 'cash_flow', 'finance', 'balance', 'bank_indicator',
                 'query', 'Query', 'QueryResult', 'Table', 'TableNamespace',
                 'get_all_securities', 'get_all_trade_days', 'ProApi',
                 'StockDBClient', 'call_remote', 'eval_remote'):
        show(name)
    # 试 query 框架（构造一个查询，看返回什么——不消耗限额的构造）
    print("\n" + "=" * 56 + "\n🔬 试构造 query（只构造不执行）\n" + "=" * 56)
    for expr in ('finance', 'balance', 'cash_flow', 'fundamentals'):
        try:
            q = stock_sdk.query(expr)
            print(f"  query({expr}): {type(q)} -> {str(q)[:200]}")
        except Exception as e:
            print(f"  query({expr}): {e}")
    # 试 rd.get 模式（本地表）
    try:
        rd = stock_sdk.get_default_raw_rd() if hasattr(stock_sdk, 'get_default_raw_rd') else stock_sdk.rd
        for t in ('finance', 'balance', 'cash_flow', '日k'):
            try:
                r = rd.get(f"{t}:000063:2025*").do()
                print(f"  rd.get({t}:000063:2025*): {len(r) if hasattr(r,'__len__') else r} 条")
            except Exception as e:
                print(f"  rd.get({t}...): {e}")
    except Exception as e:
        print(f"  rd: {e}")


if __name__ == '__main__':
    main()
