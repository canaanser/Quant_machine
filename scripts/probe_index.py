# -*- coding: utf-8 -*-
"""探测 stockdb 里的指数代码（2026-08-28 小二陈）
三大指数在 stockdb 的代码格式未知（999999/399001/399006 无数据），
一次试全候选：000300/000016/000905(常见指数6位) + 带前缀格式。
用法（Windows）：python scripts/probe_index.py
"""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "pybao"))


def main():
    from stock_sdk import get_default_client
    client = get_default_client()
    rd = client.rd if hasattr(client, "rd") else client

    candidates = [
        '000300', '000016', '000905', '000852',      # 沪深300/上证50/中证500/中证1000
        '399001', '399006', '399005',                # 深成/创业板/中小板
        'sh000001', '000001.SH', '999999',           # 上证指数候选格式
        'sh000300', '000300.SH',                     # 沪深300 带前缀
    ]
    print("探测指数代码（2024-01 月数据条数）：")
    for c in candidates:
        try:
            res = rd.get_data(c, start='20240101', end='20240201', frequency='1d', as_df=False)
            if isinstance(res, dict):
                for k, v in res.items():
                    n = len(v) if isinstance(v, (list, tuple)) else 1
                    print(f'  {c} -> key={k}: {n} 条')
            else:
                n = len(res) if res else 0
                print(f'  {c}: {n} 条')
        except Exception as e:
            print(f'  {c}: 失败 {type(e).__name__}: {str(e)[:60]}')


if __name__ == "__main__":
    main()
