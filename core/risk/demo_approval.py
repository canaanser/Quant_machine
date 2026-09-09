# -*- coding: utf-8 -*-
"""④ demo: 全局风控 + 下单审批层 (core/risk/demo_approval.py)
仅测试用, 不接实盘。替代"原风控/审批"在测试流水线 B 中运行:
  输入: 计划(plan)、质量分、市场环境(大盘涨跌/信号数)、组合总预算
  输出: 修正后的下单清单(含 仓位系数/拒绝/降档 理由), 与流水线 A(原样)对照
规则(可解释, 不做黑箱):
  全局层: 环境差(大盘跌 & 全池信号多=恐慌/出血日) → 组合总仓上限打折
  信号层: 质量分高 → 单票仓位系数放大; 分低 → 收缩; 负分 → 拒买或降为观察
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
FUNDA = ROOT / "outputs" / "funda_rank6.json"


def _score_map():
    try:
        rows = json.load(open(FUNDA, encoding="utf-8"))
        return {r["code"]: r.get("score", 0.5) for r in rows}
    except Exception:
        return {}


def global_cap(market_pct: float, signal_count: int) -> tuple:
    """环境→组合总仓系数. 返回 (cap_mult, 理由)"""
    if market_pct <= -1.5 and signal_count >= 10:
        return 0.5, f"恐慌日(大盘{market_pct:+.1f}% & {signal_count}信号): 总仓砍半"
    if market_pct <= -0.8 or signal_count >= 15:
        return 0.7, f"偏弱(大盘{market_pct:+.1f}%/信号{signal_count}): 总仓×0.7"
    return 1.0, f"中性({market_pct:+.1f}% / {signal_count}信号): 满额"


def position_coef(score: float) -> float:
    """质量分(财报0~1)→单票系数 0.6~1.4"""
    return max(0.6, min(1.4, 1.0 + (score - 0.5) * 0.6))


def approve_plan(plan_rows, capital: float, market_pct: float = 0.0,
                 signal_count: int = 10, score_map=None):
    """plan_rows: orderfile.read_plan → [(code,side,shares,price,name)]
    返回 (orders, notes, summary)
    orders: [(action, code, shares, px, name, reason)]  // SELL 原样带过
    """
    score_map = score_map or _score_map()
    buys = [r for r in plan_rows if r[1] == "buy"]
    sells = [r for r in plan_rows if r[1] != "buy"]
    cap_mult, g_reason = global_cap(market_pct, signal_count)
    budget = capital * cap_mult
    # 质量加权分配预算
    wsum = 0.0
    w = {}
    notes = []
    for code, side, shares, px, name in buys:
        sc = score_map.get(code, 0.5)
        if sc <= 0.1:
            w[code] = 0.0
            notes.append(f"{code}: 质量分{sc:.2f} → 拒买(转观察)")
            continue
        c = position_coef(sc)
        w[code] = c
        wsum += c
        notes.append(f"{code}: 质量{sc:.2f} → 系数{c:.2f}")
    orders = []
    alloc_sum = 0.0
    for code, side, shares, px, name in buys:
        if w.get(code, 0) <= 0:
            orders.append(("OBS", code, 0, px, name, "拒买-观察"))
            continue
        alloc = budget * w[code] / wsum
        lot = 200 if code.startswith(("688", "689", "301", "300")) else 100
        lot = 100 if code.startswith(("300", "301")) else lot  # 创业100股
        n = int(alloc / px) // lot * lot
        orders.append(("BUY", code, n, px, name,
                       f"预算{alloc:,.0f}→{n}股(系数{w[code]:.2f}×总仓{cap_mult:.1f})"))
        alloc_sum += n * px
    for code, side, shares, px, name in sells:
        orders.append(("SELL", code, shares, px, name, "原样带过"))
    summary = dict(cap_mult=cap_mult, g_reason=g_reason,
                   budget=budget, used=alloc_sum,
                   buys=len([o for o in orders if o[0] == "BUY"]),
                   obs=len([o for o in orders if o[0] == "OBS"]))
    return orders, notes, summary
