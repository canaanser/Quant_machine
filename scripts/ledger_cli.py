# -*- coding: utf-8 -*-
r"""台账命令行入口 (模块化阶段1)
  buy  <code> <date> <shares> <price> [name]   记买入
  sell <code> <date> <price> <reason>          记卖出(防崩/峰顶/滞涨/手动)
  status [--px "code:px,code:px"]              查持仓状态(带现价算防崩/峰顶)
  open                                    打印持仓清单
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.trade.ledger import buy, sell, status, _load


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    cmd = args[0]
    if cmd == "buy":
        c, d, sh, pr = args[1], args[2], int(args[3]), float(args[4])
        nm = args[5] if len(args) > 5 else ""
        buy(c, d, sh, pr, nm)
        print(f"[OK] 已记买入 {c} {sh}股 @{pr} ({d})")
    elif cmd == "sell":
        c, d, pr, why = args[1], args[2], float(args[3]), args[4]
        r = sell(c, d, pr, why)
        print(f"[OK] 已平仓 {c} @{pr} 原因={why} 盈亏={r*100:+.1f}%")
    elif cmd == "status":
        px = {}
        for kv in (args[1:] or []):
            if kv.startswith("--px="):
                for pair in kv[5:].split(","):
                    k, v = pair.split(":")
                    px[k] = float(v)
        rows = status(px)
        if not rows:
            print("空仓")
        for r in rows:
            print(f"{r['code']} {r['name']:<8} 成本{r['cost']:.2f} 防崩{r['fangbeng']:.2f} "
                  + (f"现价{r['px']} 盈亏{r['pnl_pct']:+.1f}% | {r['action']}"
                     if 'px' in r else f"| {r['note']}"))
    elif cmd == "open":
        for code, p in _load()["positions"].items():
            print(f"{code} {p.get('name','')} {p['shares']}股 成本{p['cost']:.2f} 买日{p['date']}")


if __name__ == "__main__":
    main()
