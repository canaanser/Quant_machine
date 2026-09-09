# -*- coding: utf-8 -*-
r"""stockdb 实时取价(主源) — 基于本地 stockdb.pyd 的 get_last_tick
用法(Windows cmd, 必须 E:\python, 3rdpart_pybao 是 Windows 原生库):
  E:\python\python.exe -B scripts\rt_stockdb.py --codes 600633,000063
  E:\python\python.exe -B scripts\rt_stockdb.py --file outputs\friday40_codes.txt
输出: 代码 现价(最新tick) 最高 最低 量 时间
"""
import argparse, io, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "3rdpart_pybao"))
import stockdb

NAMES = {'600633': '浙数文化'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--codes', default='')
    ap.add_argument('--file', default='')
    a = ap.parse_args()
    codes = [c.strip() for c in a.codes.split(',') if c.strip()]
    if a.file:
        codes += [ln.strip() for ln in open(a.file, encoding='utf-8') if ln.strip()]
    if not codes:
        print('给 --codes 或 --file'); return
    print(f"{'代码':<8}{'现价':>10}{'最高':>10}{'最低':>10}{'量':>12}  tick时间", flush=True)

    def one(c):
        try:
            r = stockdb.get_last_tick(c, count=1, df=False)
            if isinstance(r, dict) and 'error' in r:
                return f"{c:<8}  错误: {r['error']}"
            if not r:
                return f"{c:<8}  无数据"
            t = r[0]
            return (f"{c:<8}{t.get('current',0):>10.2f}{t.get('high',0):>10.2f}"
                    f"{t.get('low',0):>10.2f}{t.get('volume',0):>12.0f}  {t.get('time','')}")
        except Exception as e:
            return f"{c:<8}  异常: {repr(e)[:80]}"

    with ThreadPoolExecutor(max_workers=8) as ex:
        for line in ex.map(one, codes):
            print(line, flush=True)


if __name__ == '__main__':
    main()
