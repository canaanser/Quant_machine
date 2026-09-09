# -*- coding: utf-8 -*-
"""demo: 双流水线对照(测试专用)
A 流水线: 现有策略配置 → 原样下单文件单(不动风控/审批)
B 流水线: 同一配置 → 新"全局风控+下单审批"(core/risk/demo_approval) 替代原风控/审批 → 修正文件单
产出到 outputs/demo/ (A/B 各一个 .order.csv), 控制台对照。

用法(Windows):
  python -B scripts/demo_two_pipelines.py
  [--plan outputs/order_0908_plan.csv] [--capital 160000]
  [--market-pct -0.04] [--signal-count 17]
"""
import io
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.lib import orderfile
from core.lib.dbfread import read_dbf
from core.risk.demo_approval import approve_plan
import datetime

OUT = PROJECT_ROOT / "outputs" / "demo"


def main():
    args = sys.argv[1:]
    plan = "outputs/order_0908_plan.csv"
    capital = 160000.0
    mpct, nsig = 0.0, 10
    for i, a in enumerate(args):
        if a == "--plan" and i + 1 < len(args):
            plan = args[i + 1]
        if a == "--capital" and i + 1 < len(args):
            capital = float(args[i + 1])
        if a == "--market-pct" and i + 1 < len(args):
            mpct = float(args[i + 1])
        if a == "--signal-count" and i + 1 < len(args):
            nsig = int(args[i + 1])
    OUT.mkdir(parents=True, exist_ok=True)
    rows = orderfile.read_plan(PROJECT_ROOT / plan)
    account = json.load(open(PROJECT_ROOT / "outputs/emq_config.json", encoding="utf-8"))["account_id"]

    # A 流水线: 原样(按 plan 股数)
    orders_a = [(r[1].upper(), r[0], r[2], r[3] or 0.0, r[4]) for r in rows]
    fa = orderfile.build_and_write(OUT / "A", account, orders_a, make_fin=False)

    # B 流水线: 新风控+审批
    orders_b, notes, summary = approve_plan(rows, capital, mpct, nsig)
    fb = orderfile.build_and_write(OUT / "B", account,
                                   [(o[0], o[1], o[2], o[3], o[4]) for o in orders_b
                                    if o[0] in ("BUY", "SELL")], make_fin=False)

    print(f"demo 双流水线 | 资本 {capital:,.0f} | 环境: 大盘{mpct:+.2f}% 信号{nsig}")
    print(f"[A] 原样文件单: {fa}")
    print(f"[B] 新风控文件单: {fb}")
    print(f"\n[B] 风控判定: {summary['g_reason']}")
    total_a = sum(o[2] * o[3] for o in orders_a if o[0] != "SELL")
    total_b = sum(o[2] * o[3] for o in orders_b if o[0] in ("BUY", "SELL") and o[2])
    print(f"[A] 计划买入额 ≈ {total_a:,.0f}  {len(orders_a)}笔")
    print(f"[B] 审批后买入额 ≈ {total_b:,.0f}(总仓{summary['cap_mult']:.1f}×{summary['budget']:,.0f}预算, 用{summary['used']:,.0f})  {summary['buys']}买/{summary['obs']}观察")
    print("\n[B] 逐票审批:")
    for o in orders_b:
        print(f"  {o[0]:<4} {o[1]} {o[2]:>5}股 @{o[3]:>7.2f}  {o[5]}")
    print("\n对照: A 原样无风控; B 新增全局降档/质量加权/拒买 — 均只产出文件, 未触碰实盘/scan。")


if __name__ == "__main__":
    main()
