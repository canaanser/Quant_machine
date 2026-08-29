# -*- coding: utf-8 -*-
"""财务拉取诊断（2026-08-30）：不吞异常，打印每个表/每次调用的真实错误
目的：确定 get_fundamentals 5 张表的正确调用（文档用法 vs 实际服务端差异）
用法（Windows）：python -B scripts/fundamentals_diag.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'pybao'))
import stock_sdk

CODE = '000063.XSHE'


def main():
    print(f"诊断代码: {CODE}")
    # 1. 表对象是否存在 + 属性
    for tname in ('valuation', 'indicator', 'income', 'cash_flow', 'balance'):
        tbl = getattr(stock_sdk, tname, None)
        print(f"\n=== 表 {tname}: {tbl} ===")
        if tbl is None:
            print("  不存在!")
            continue
        # 表的 code 属性
        try:
            c = getattr(tbl, 'code')
            print(f"  tbl.code = {c} (type={type(c)})")
        except Exception as e:
            print(f"  tbl.code 异常: {type(e).__name__}: {e}")
        # 2. 构造 query
        try:
            q = stock_sdk.query(tbl).filter(tbl.code == CODE)
            print(f"  query(tbl).filter(tbl.code=={CODE}) 构造 OK: {q}")
        except Exception as e:
            print(f"  query 构造失败: {type(e).__name__}: {e}")
            continue
        # 3. 试 date 和 statDate 两种模式
        for mode, p in (('date', '2025-12-31'), ('statDate', '2024q4')):
            try:
                r = stock_sdk.get_fundamentals(q, **{mode: p})
                if hasattr(r, 'to_string') or hasattr(r, 'columns'):
                    print(f"  ✅ {mode}={p}: DataFrame {getattr(r,'shape','?')} 列={list(getattr(r,'columns',[]))[:12]}")
                else:
                    print(f"  {mode}={p}: {type(r)} -> {str(r)[:200]}")
            except Exception as e:
                print(f"  ❌ {mode}={p} 异常: {type(e).__name__}: {e}")


if __name__ == '__main__':
    main()
