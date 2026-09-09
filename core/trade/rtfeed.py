# -*- coding: utf-8 -*-
r"""实时行情源 core/rtfeed.py (模块化阶段1)
腾讯 qt.gtimg.cn: 盘中实时, 收盘后=当日收盘。与本地库9/7口径核对一致(2026-09-08)。
fetch(codes) -> {code: {name,px,prev,open,chg,pct,high,low,ts}}
"""
import urllib.request


def prefix(code):
    if code.startswith(('5', '6', '9')):
        return 'sh' + code
    if code.startswith(('0', '2', '3')):
        return 'sz' + code
    return 'sh' + code


def fetch(codes, timeout=8):
    if isinstance(codes, str):
        codes = [codes]
    syms = ','.join(prefix(c) for c in codes)
    url = 'http://qt.gtimg.cn/q=' + syms
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    text = raw.decode('gbk', errors='replace')
    out = {}
    for line in text.strip().split(';'):
        line = line.strip()
        if not line.startswith('v_'):
            continue
        body = line.split('="', 1)[1].rstrip('"')
        f = body.split('~')
        if len(f) < 35:
            continue
        out[f[2]] = dict(name=f[1], px=float(f[3]), prev=float(f[4]),
                         open=float(f[5]), chg=float(f[31]), pct=float(f[32]),
                         high=float(f[33]), low=float(f[34]), ts=f[30])
    return out
