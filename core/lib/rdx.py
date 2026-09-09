# -*- coding: utf-8 -*-
"""stockdb 原生 rd 查询封装 (tools/toolkit/rdx.py)
用法: rdx.get("日k","600633","20260907>20260908")
      rdx.day_range(code, start, end) / rdx.universe()
底层: 3rdpart_pybao/stockdb (Windows pyd) 的原生 rd.get (毫秒级, 前缀/区间/通配)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
_PYBAO = str(ROOT / "3rdpart_pybao")
if _PYBAO not in sys.path:
    sys.path.insert(0, _PYBAO)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _rd():
    import stockdb
    return stockdb.rd


def get(kind, target, window):
    """原生: rd.get("日k"/"分钟k"/..., code|prefix, "start>end" | "日期93*" | 单日)"""
    return _rd().get(kind, target, window)


def day_rows(code, date, kind="日k"):
    """单日K → [{date,code,open,high,low,close,volume,...}]
    容错: raw 可能是 list / dict / 可迭代的 QueryResult(每项 dict 或 [id,dict])"""
    raw = get(kind, code, f"{date}>{date}")
    items = []
    if isinstance(raw, dict) and "date" not in raw:
        raw = []
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, list) and len(x) > 1 and isinstance(x[1], dict):
                items.append(x[1])
            elif isinstance(x, dict):
                items.append(x)
    elif isinstance(raw, dict):
        items = [raw]
    elif hasattr(raw, "keys") and hasattr(raw, "vals"):
        # QueryResult 单行网格: keys()=列名 vals()=本行值(单日查询恰1行)
        ks = list(raw.keys())
        vs = list(raw.vals())
        if ks and len(ks) == len(vs):
            items.append(dict(zip(ks, vs)))
    return items


def universe():
    """全市场代码字典 rd.get('股票代码') → {首位数:[codes,...]}"""
    d = get("股票代码", None, None) if False else _rd().get("股票代码")
    return d if isinstance(d, dict) else {}
