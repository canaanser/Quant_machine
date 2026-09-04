# -*- coding: utf-8 -*-
"""
从 stockdb 枚举全市场 A 股代码（2026-08-28 小二陈）

原理：stockdb 底层是 LevelDB，键格式为 '复权:{code}:{date}'。
      rd.get('复权*') 通配符枚举全部键 → 从键中提取 6 位股票代码。
      —— 不用挨个填名单，直接从数据引擎要全市场清单。

用法（Windows 上，stockdb 服务运行中）：
    python scripts/dump_stock_list.py [--out data/stock_list.txt]

输出：data/stock_list.txt（每行一个 6 位代码），供扫描器 --pool all 使用。
"""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "pybao"))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(PROJECT / "data" / "stock_list.txt"))
    args = parser.parse_args()

    from stock_sdk import get_default_client
    client = get_default_client()
    rd = client.rd if hasattr(client, "rd") else client

    print("枚举复权表全部键（rd.get('复权*')）...")
    raw = rd.get("复权*")
    if isinstance(raw, dict):
        raw = raw.get("cum", raw)

    codes = set()
    for item in raw:
        key = item[0] if isinstance(item, (list, tuple)) else item
        parts = str(key).split(":")
        if len(parts) >= 2:
            c = parts[1]
            if c.isdigit() and len(c) == 6:
                codes.add(c)
    codes = sorted(codes)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(codes), encoding="utf-8")
    print(f"全市场 A 股代码: {len(codes)} 只 → {out}")
    print("前 10 只:", codes[:10])


if __name__ == "__main__":
    main()
