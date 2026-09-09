# -*- coding: utf-8 -*-
r"""尾盘一键生成文件单(生产用例, 用 toolkit) — 2026-09-08 整理
逻辑:
  1) 实时价: toolkit.quotes.live_px(默认腾讯, 可选 stockdb)
  2) 买入: 读 plan csv → 实时价当限价
  3) 卖出: 台账持仓按实时价判防崩/峰顶 → 触发即生成卖出
  4) 产出 .order.csv: --go 写进 scan_dir(emq_config 或 --out) 并自动 .fin; 否则只写暂存
防重: 当日 --go 只放一次(orders_sent.json)
用法(Windows, 尾盘14:58):
  E:\python\python.exe -B scripts\final_order.py --plan outputs\order_0908_plan.csv
      [--at 1458] [--go] [--source tencent|stockdb] [--out <目录>] [--no-fin]
"""
import io
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.trade.ledger import _load, status
from core.lib import orderfile, quotes
from core.trade.file_order_broker import FileOrderBroker

CFG = PROJECT_ROOT / "outputs" / "emq_config.json"
NAMES = {"603256": "宏和科技", "301358": "湖南裕能", "002595": "豪迈科技",
         "688775": "影石创新", "688702": "盛科通信-U", "688172": "燕东微"}


def cfg():
    return json.load(open(CFG, encoding="utf-8"))


def main():
    args = sys.argv[1:]
    plan = out_ov = at_time = None
    source = "tencent"
    go_live = "--go" in args
    no_fin = "--no-fin" in args
    for i, a in enumerate(args):
        if a == "--plan" and i + 1 < len(args):
            plan = args[i + 1]
        if a == "--out" and i + 1 < len(args):
            out_ov = args[i + 1]
        if a == "--at" and i + 1 < len(args):
            at_time = args[i + 1]
        if a == "--source" and i + 1 < len(args):
            source = args[i + 1]
    if at_time:
        import datetime
        now = datetime.datetime.now()
        tgt = now.replace(hour=int(at_time[:2]), minute=int(at_time[2:4]),
                          second=5, microsecond=0)
        if tgt < now:
            tgt += datetime.timedelta(days=1)
        print(f"[定时] 现在{now:%H:%M:%S}, 等 {(tgt-now).total_seconds():.0f}s 到 {tgt:%H:%M:%S} 放单", flush=True)
        time.sleep(max(0, (tgt - now).total_seconds()))
    c = cfg()
    account = c["account_id"]
    scan_dir = Path(out_ov) if out_ov else (
        Path(c["scan_dir"]) if go_live else PROJECT_ROOT / "Stream" / "staging")
    if not plan:
        print(__doc__)
        return
    # 防重: 当日 --go 仅一次
    sent_log = PROJECT_ROOT / "outputs" / "orders_sent.json"
    if go_live and sent_log.exists():
        sent = json.load(open(sent_log, encoding="utf-8"))
        if any(x.get("date") == time.strftime("%Y%m%d") for x in sent):
            print("[防重] 今天已发过 --go, 拒绝重复放单 (重发需删 outputs/orders_sent.json)")
            return
    # 需要实时价的代码: 买入+持仓
    codes = []
    buys = []
    rows = orderfile.read_plan(plan)
    for code, side, shares, px, name in rows:
        if side == "buy":
            buys.append((code, shares, name or NAMES.get(code, "")))
            codes.append(code)
    for k in _load()["positions"]:
        codes.append(k)
    codes = sorted(set(codes))
    px = quotes.live_px(codes, prefer=source)
    print("实时价: " + " ".join(f"{k}={v}" for k, v in px.items()), flush=True)
    orders = []
    for code, shares, name in buys:
        if code not in px:
            print(f"  跳过买入 {code} 无实时价")
            continue
        orders.append(("BUY", code, shares, px[code], name))
        print(f"  买入 {code} {NAMES.get(code,name)} {shares}股 @{px[code]:.2f}(实时价)", flush=True)
    for r in status(px):
        if "px" not in r or not r["action"].startswith("[!!]"):
            continue
        orders.append(("SELL", r["code"], r["shares"], r["px"], NAMES.get(r["code"], "")))
        print(f"  卖出 {r['code']} {r['shares']}股 @{r['px']:.2f} | {r['action']}", flush=True)
    if not orders:
        print("无操作(无买点且持仓未触发卖出)")
        return
    if not go_live and not out_ov:
        print("\n[安全] 未加 --go: 只写暂存区 Stream/staging (不会被执行)")
        print("      14:58 确认放单时加 --go 重跑(写进 scan 目录并自动 .fin)")
    # 统一走 FileOrderBroker(只做执行)
    broker = FileOrderBroker(scan_dir=str(scan_dir), account_id=account)
    make_fin = go_live and not no_fin
    sids = broker.place_batch(orders, make_fin=make_fin)
    fpath = scan_dir  # 文件落目录
    print(f"已通过 FileOrderBroker 放单 {len(sids)} 笔 → {scan_dir}"
          + (" (+.fin 自动)" if make_fin else " (未建 .fin, 仅暂存)"))
    if go_live:
        sent = []
        if sent_log.exists():
            sent = json.load(open(sent_log, encoding="utf-8"))
        sent.append(dict(date=time.strftime("%Y%m%d"), scan_dir=str(scan_dir),
                         sids=sids, rows=[o[0] + o[1] for o in orders]))
        json.dump(sent, open(sent_log, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
