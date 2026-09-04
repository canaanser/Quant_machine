# -*- coding: utf-8 -*-
"""探测 v3：只构造 query 链 + 看 .url（不执行、不消耗限额）（2026-08-30）
目标：从查询 URL 反推 get_fundamentals(query_object) 的正确参数格式
安全：只调 .url/.str（构造查询字符串），绝不 .do() 执行
用法（Windows）：python -B scripts/probe_online_api3.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'pybao'))
import stock_sdk


def safe_url(label, obj):
    """打印对象及 url（只构造，不执行）"""
    try:
        s = str(obj)
        u = getattr(obj, 'url', None)
        print(f"  {label}: {s}")
        if u:
            print(f"      url: {u}")
    except Exception as e:
        print(f"  {label}: 异常 {e}")


def main():
    print("== 构造链探索（零限额消耗）==")
    # 1. query('finance') 原始
    try:
        q0 = stock_sdk.query('finance')
        safe_url("query('finance')", q0)
        # 2. 各方法返回什么（to_code/filter/limit/order_by/offset）
        for mname in ('to_code', 'filter', 'limit', 'order_by', 'offset'):
            fn = getattr(q0, mname, None)
            if fn is None:
                print(f"  query(finance).{mname}: 不存在")
                continue
            # 试常见参数
            for args in (('000063',), ({'code': '000063'},), (10,), ('date',)):
                try:
                    r = fn(*args)
                    safe_url(f"query(finance).{mname}{args}", r)
                    break  # 第一个成功的
                except Exception as e:
                    print(f"  query(finance).{mname}{args}: {str(e)[:80]}")
    except Exception as e:
        print(f"  query('finance'): {e}")

    # 3. balance / cash_flow Table 的 to_code
    for tname in ('balance', 'cash_flow'):
        t = getattr(stock_sdk, tname, None)
        if t is None:
            continue
        try:
            r = t.to_code('000063')
            safe_url(f"{tname}.to_code('000063')", r)
        except Exception as e:
            print(f"  {tname}.to_code('000063'): {str(e)[:80]}")

    # 4. finance.run_query
    try:
        r = stock_sdk.finance.run_query(stock_sdk.query('finance'))
        safe_url("finance.run_query(query('finance'))", r)
    except Exception as e:
        print(f"  finance.run_query: {str(e)[:80]}")


if __name__ == '__main__':
    main()
