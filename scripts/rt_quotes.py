# -*- coding: utf-8 -*-
r"""实时行情快照工具 — 老板盘中/快收盘用 (2026-09-08)
数据源: core/rtfeed.py → 腾讯 qt.gtimg.cn (收盘后给当日收盘, 盘中给实时)
用法 (Windows cmd):
  E:\python\python.exe -B scripts\rt_quotes.py --codes 002080,688506
  E:\python\python.exe -B scripts\rt_quotes.py --file outputs\friday40_codes.txt
"""
import argparse, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from core.trade.rtfeed import fetch, prefix


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--codes', default='', help='逗号分隔代码')
    ap.add_argument('--file', default='', help='每行一个代码的文件')
    a = ap.parse_args()
    codes = [c.strip() for c in a.codes.split(',') if c.strip()]
    if a.file:
        codes += [ln.strip() for ln in open(a.file, encoding='utf-8') if ln.strip()]
    if not codes:
        print('给 --codes 或 --file'); return
    rows = fetch(codes)
    print(f"{'代码':<8}{'名称':<12}{'现价':>10}{'涨跌%':>9}{'今开':>10}{'最高':>10}{'最低':>10}  时间", flush=True)
    ups = downs = flats = 0
    tot = 0.0
    for c in codes:
        r = rows.get(c)
        if not r:
            print(f"{c:<8}未取到"); continue
        if r['pct'] > 0.05: ups += 1
        elif r['pct'] < -0.05: downs += 1
        else: flats += 1
        tot += r['pct']
        nm = r['name'][:8]
        print(f"{c:<8}{nm:<12}{r['px']:>10.2f}{r['pct']:>+8.2f}%{r['open']:>10.2f}"
              f"{r['high']:>10.2f}{r['low']:>10.2f}  {r['ts']}", flush=True)
    n = len([1 for c in codes if c in rows])
    if n:
        print(f"\n共{n}只: 涨{ups} 跌{downs} 平{flats} | 平均涨跌{tot/n:+.2f}% (数据时间见上)", flush=True)


if __name__ == '__main__':
    main()
