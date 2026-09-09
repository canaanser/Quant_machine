# -*- coding: utf-8 -*-
"""close_check — 收盘核对报告 (2026-09-09)
盘后/执行后跑: 对账 东财归档(cash/nav/pnl) + ledger 持仓权重, 输出摘要并落盘留痕。
用法: python -B scripts/close_check.py [--date 20260910]
"""
import csv, json, sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core" / "lib"))
from core.lib.emq_arch import latest_date, read_cash
from core.trade.ledger import _load


def close_px(date):
    from core.lib import rdx
    pos = _load()["positions"]
    out = {}
    for c in pos:
        rows = rdx.day_rows(c, date)
        if rows:
            out[c] = float(rows[0].get("close"))
    return out, pos


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    date = a.date or latest_date()
    if not date:
        print("无归档数据")
        return
    avail, nav = read_cash(date)
    px, pos = close_px(date)
    lines = [f"== 收盘核对 {date} ==", f"账户: 净值 {nav:,.0f} | 可用现金 {avail:,.0f}"]
    mv = 0.0
    for c, p in pos.items():
        cur = px.get(c, p["cost"])
        m = p["shares"] * cur
        mv += m
        pct = m / nav * 100 if nav else 0
        lines.append(f"  {c} {p.get('name','')} {p['shares']}股 @{cur:.2f} ≈{m:,.0f} ({pct:.1f}%)")
    lines.append(f"持仓市值≈{mv:,.0f} 占比 {mv/nav*100 if nav else 0:.1f}%")
    out = "\n".join(lines)
    print(out)
    (ROOT / "outputs" / f"close_report_{date}.txt").write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
