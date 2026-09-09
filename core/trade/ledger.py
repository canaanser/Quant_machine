# -*- coding: utf-8 -*-
r"""模拟盘台账 core/ledger.py (2026-09-08 模块化阶段1)
记每笔买/卖, 自动算每仓: 成本/防崩价(-12%)/浮盈/峰顶状态/滞涨天数。
用法(Windows cmd):
  E:\python\python.exe -B -c "from core.trade.ledger import *; buy('603256','20260908',400,123.82)"
  E:\python\python.exe -B scripts/ledger_cli.py buy 603256 20260908 400 123.82
  E:\python\python.exe -B scripts/ledger_cli.py sell 603256 20260908 132.0 峰顶
  E:\python\python.exe -B scripts/ledger_cli.py status --px "603256:130.0,301358:50.0"
存储: outputs/ledger.json  {positions:{code:{...}}, trades:[...]}
"""
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
LEDGER = PROJECT_ROOT / "outputs" / "ledger.json"

from core.risk.sellrules import (FANG_BENG, FANG_BENG_PNL, PNL_START, RETREAT,
                                STALL_DAYS, HHD_HIGH, decide, fangbeng_price)


def _load():
    if LEDGER.exists():
        try:
            return json.load(open(LEDGER, encoding="utf-8"))
        except Exception:
            pass
    return {"positions": {}, "trades": []}


def _save(data):
    tmp = str(LEDGER) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, LEDGER)


def buy(code, date, shares, price, name=""):
    """开仓/加仓(加仓按均价合并)。shares=股数, price=每股成交价"""
    d = _load()
    p = d["positions"].get(code)
    if p:  # 加仓: 加权平均成本
        old = p["shares"] * p["cost"]
        p["cost"] = round((old + shares * price) / (p["shares"] + shares), 4)
        p["shares"] += shares
        p["date"] = date
    else:
        d["positions"][code] = dict(code=code, name=name, date=date,
                                    shares=shares, cost=round(price, 4),
                                    peak=round(price, 4), hhd=0, hi_days=0)
    d["trades"].append(dict(date=date, code=code, action="buy", shares=shares, price=price))
    _save(d)
    return p


def sell(code, date, price, reason):
    """平仓。reason ∈ 防崩/峰顶/滞涨/手动"""
    d = _load()
    p = d["positions"].pop(code, None)
    if not p:
        return None
    ret = price / p["cost"] - 1
    d["trades"].append(dict(date=date, code=code, action="sell",
                            shares=p["shares"], price=price, reason=reason,
                            cost=p["cost"], ret_pct=round(ret * 100, 2)))
    _save(d)
    return ret


def status(px_map=None):
    """px_map: {code: 今日收盘/现价}。返回每仓: 浮盈/防崩价/是否破防崩/峰顶状态建议"""
    d = _load()
    out = []
    for code, p in d["positions"].items():
        px = (px_map or {}).get(code)
        cost = p["cost"]
        fb = round(cost * FANG_BENG, 2)
        rec = dict(code=code, name=p.get("name", ""), shares=p["shares"],
                   cost=cost, fangbeng=fb, date=p.get("date"))
        if px is None:
            rec["note"] = "缺现价, 只列防崩价"
            out.append(rec)
            continue
        rec["px"] = px
        pnl = px / cost - 1
        rec["pnl_pct"] = round(pnl * 100, 2)
        if px > p.get("peak", cost):
            p["peak"], p["hhd"] = round(px, 4), 0
        else:
            p["hhd"] = p.get("hhd", 0) + 1
        rec["peak"] = p.get("peak")
        rec["hhd"] = p.get("hhd")
        act = decide(cost, px, p.get("peak", cost), p.get("hhd", 0))
        if act == "防崩":
            rec["action"] = "[!!] 破防崩! 收盘价≤防崩价 → 次日开盘卖"
        elif act == "滞涨":
            rec["action"] = f"[!!] 滞涨{STALL_DAYS}日 → 卖"
        elif act == "峰顶":
            rec["action"] = f"[!!] 跌破持有新高×0.98(高位≥{HHD_HIGH}日) → 卖"
        elif pnl >= PNL_START:
            rec["action"] = f"浮盈{pnl*100:.0f}%≥30%: 峰顶跟踪中(持有新高{p['peak']})"
        else:
            rec["action"] = f"拿住(浮盈{pnl*100:.1f}%), 防崩价 {fb}"
        _save(d)
        out.append(rec)
    return out
