# -*- coding: utf-8 -*-
"""文件单 .order.csv 通用逻辑 (tools/toolkit/orderfile.py)
plan/委托生成/落盘 — emq_order 与 final_order 共用, 单一真源。
"""
import csv
import time
from pathlib import Path


def to_symbol(code):
    code = str(code).zfill(6)
    return ("SHSE." if code[0] in ("6", "9", "5") else "SZSE.") + code


def read_plan(path):
    """读下单计划 csv: code,side(buy/sell),shares,price,name → [(code,side,shares,price,name)]"""
    out = []
    with open(path, encoding="utf-8-sig") as f:
        for ln in csv.reader(f):
            if not ln or not ln[0].strip() or ln[0].strip().lower() == "code":
                continue
            code, side, shares, price, name = (ln + [""] * 5)[:5]
            out.append((code.strip(), side.strip(), int(float(shares)),
                        float(price) if price else None, name.strip()))
    return out


def build_and_write(out_dir, account, orders, make_fin=True):
    """orders: [(side,buy/sell 'BUY'/'SELL', code, shares, px, name)]
    写入 out_dir/<ts>.order.csv, 返回路径(可另建 .fin)"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S") + f".{int(time.time()*1000)%1000:03d}"
    fname = f"{ts}.order.csv"
    fpath = out_dir / fname
    with open(fpath, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sid", "account_id", "symbol", "volume", "order_type",
                    "order_business(order_biz)", "price", "comment"])
        for k, (side, code, shares, px, name) in enumerate(orders, 1):
            biz = "1" if side == "BUY" else "2"
            sid = side + ts.replace("-", "").replace(":", "") + str(k)
            w.writerow([sid, account, to_symbol(code), shares, 1, biz,
                        round(px, 2) if px is not None else "", name])
    if make_fin:
        Path(str(fpath) + ".fin").touch()
    return fpath
