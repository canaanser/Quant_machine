# -*- coding: utf-8 -*-
r"""计划→文件单生成(生产用例, 用 toolkit.orderfile) — 2026-09-08 整理
用法(Windows):
  E:\python\python.exe -B scripts\emq_order.py --plan outputs\order_0908_plan.csv [--out Stream\staging]
生成 <时间戳>.order.csv 到 out(不建 .fin, 放单时再建 .fin 由终端执行)
plan 格式: code,side(buy/sell),shares,price,name
"""
import io
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from core.lib import orderfile


def main():
    args = sys.argv[1:]
    plan = out = account = None
    for i, a in enumerate(args):
        if a == "--plan" and i + 1 < len(args):
            plan = args[i + 1]
        if a == "--out" and i + 1 < len(args):
            out = args[i + 1]
        if a == "--account" and i + 1 < len(args):
            account = args[i + 1]
    if not plan:
        print(__doc__)
        return
    if not out:
        out = "Stream/staging"
    if not account:
        try:
            account = json.load(open(PROJECT_ROOT / "outputs/emq_config.json", encoding="utf-8"))["account_id"]
        except Exception:
            account = ""
    rows = orderfile.read_plan(plan)
    if not rows:
        print("plan 为空或全为表头")
        return
    orders = [(side.upper(), code, shares, px or 0.0, name)
              for code, side, shares, px, name in rows]
    fpath = orderfile.build_and_write(PROJECT_ROOT / out, account, orders, make_fin=False)
    print(f"已生成 {fpath}")
    print(f"放单提示: 终端扫描该目录并确认后, 创建 .fin 即执行: {fpath}.fin")


if __name__ == "__main__":
    main()
