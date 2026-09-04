# -*- coding: utf-8 -*-
"""探测 stockdb 情绪/热度相关接口（龙虎榜/资金流/两融/因子看板）
2026-08-28 小二陈（老板需求：买低不买高 + 抓重大行情起飞，用情绪数据辅助）
用法（Windows）：python -B scripts/probe_sentiment_api.py
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
        print(f"  样例: {s[:500]}")
        if hasattr(r, 'head') and hasattr(r, 'columns'):
            print(f"  列: {list(r.columns)}")
        return r
    except Exception as e:
        print(f"\n❌ {name}: {e}")
        return None


def main():
    from stock_sdk import (
        get_billboard_list, get_money_flow, get_mtss, get_factor_values,
    )
    # 龙虎榜（000063 中兴通讯，近期）
    try_call("get_billboard_list('000063', start_date='2026-08-01', end_date='2026-08-27')",
             lambda: get_billboard_list("000063", start_date="2026-08-01", end_date="2026-08-27"))
    # 资金流向
    try_call("get_money_flow('000063')",
             lambda: get_money_flow("000063"))
    # 两融
    try_call("get_mtss('000063')",
             lambda: get_mtss("000063"))
    # 因子值（情绪/热度类因子）
    try_call("get_factor_values('000063', factors=['turnover','volume_ratio','amount'])",
             lambda: get_factor_values("000063", factors=["turnover", "volume_ratio", "amount"]))


if __name__ == "__main__":
    main()
