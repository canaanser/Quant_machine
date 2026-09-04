# -*- coding: utf-8 -*-
"""探测在线选股接口：get_index_stocks / get_security_info / get_index_weights
2026-08-28 小二陈：确认指数成分选股可行性（避开微盘）与市值字段。
用法（Windows）：python -B scripts/probe_selection_api.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / 'pybao') not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / 'pybao'))

import stock_sdk


def try_call(name, fn):
    try:
        r = fn()
        print(f"\n✅ {name}:")
        print(f"  类型: {type(r)}")
        s = str(r)
        print(f"  样例: {s[:400]}")
        return r
    except Exception as e:
        print(f"\n❌ {name}: {e}")
        return None


def main():
    from stock_sdk import get_index_stocks, get_security_info, get_index_weights

    # 1. 沪深300 成分
    r1 = try_call("get_index_stocks('000300.XSHG')", lambda: get_index_stocks("000300.XSHG"))
    if r1 is not None:
        if hasattr(r1, 'head'):
            print(f"  数量: {len(r1)}  列: {list(r1.columns)}")
            print(r1.head(5).to_string())
        elif isinstance(r1, (list, tuple)):
            print(f"  数量: {len(r1)}  前10: {list(r1)[:10]}")

    # 2. 单股信息（拿市值等）
    r2 = try_call("get_security_info('000001')", lambda: get_security_info("000001"))
    if r2 is not None and hasattr(r2, 'head'):
        print(f"  列: {list(r2.columns)}")
        print(r2.to_string())

    # 3. 指数权重（可能反推市值）
    r3 = try_call("get_index_weights('000300.XSHG')", lambda: get_index_weights("000300.XSHG"))
    if r3 is not None and hasattr(r3, 'head'):
        print(f"  列: {list(r3.columns)}")
        print(r3.head(5).to_string())


if __name__ == "__main__":
    main()
