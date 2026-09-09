# -*- coding: utf-8 -*-
"""self_api — 量化系统自身对外的API(根目录, 2026-09-09 老板定)
给 duty 值守/未来模块/外部程序调用本系统的门面; 内部走 core 内核
接口冻结: 返回结构固定; core内部随便改, 接口不变不破坏调用方
"""
from core.lib import quotes
from core.trade.ledger import _load, status
from core.trade.file_order_broker import FileOrderBroker

_br = None


def market_px(codes, prefer="tencent"):
    """实时价 {code: px}(腾讯主/stockdb备)"""
    return quotes.live_px(codes, prefer=prefer)


def evaluate_holdings(px_map):
    """每仓动作: [ {code,name,shares,cost,px,pnl_pct,action,trigger} ]  trigger in (防崩/峰顶/滞涨/hold)"""
    out = []
    for r in status(px_map):
        if "action" not in r:      # 未取到价的仓
            out.append(dict(code=r["code"], name=r.get("name",""), shares=r["shares"],
                            cost=r["cost"], px=None, pnl_pct=None, action=r.get("note","缺价"), trigger="noquote"))
            continue
        act = r["action"]
        trig = "hold"
        if act.startswith("[!!]"):
            trig = ("防崩" if "防崩" in act else ("峰顶" if "峰顶" in act else "滞涨"))
        out.append(dict(code=r["code"], name=r.get("name", ""), shares=r["shares"],
                        cost=r["cost"], px=r.get("px"), pnl_pct=r.get("pnl_pct"),
                        action=act, trigger=trig))
    return out


def dispatch(actions):
    """执行一组 (action,code,shares,px,name); 返回 sids"""
    global _br
    if _br is None:
        _br = FileOrderBroker()
    orders = [(a, c, s, p, n) for (a, c, s, p, n) in actions if a in ("BUY", "SELL")]
    return _br.place_batch(orders, make_fin=True) if orders else []


def sync_fills():
    return (FileOrderBroker()).sync_fills()


def account_info():
    return (FileOrderBroker()).get_account_info()


def positions():
    return dict(_load()["positions"])
