# -*- coding: utf-8 -*-
"""尾盘自动值守 (2026-09-09 老板: 自己准时干, 不靠喊)
挂后台, 到点自动:
  14:44 取实时价 → 台账status(防崩/峰顶/滞涨)
  触发卖出 → FileOrderBroker 自动放卖单(铁律, 无需确认)
  存在 outputs/next_plan.csv(买计划, 由分析后写入) → 实时价重算 → 放买单(当日一次, 防重)
  15:00 收盘打印小结
日志: outputs/tail_auto_log.txt
"""
import io, json, sys, time, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from core.trade.ledger import _load, status
from core.trade.file_order_broker import FileOrderBroker
from core.lib import orderfile, quotes

ROOT = Path(__file__).parent.parent
LOG = ROOT / "outputs" / "tail_auto_log.txt"
NAMES = {"603256": "宏和科技", "301358": "湖南裕能", "002595": "豪迈科技",
         "688775": "影石创新", "688702": "盛科通信-U", "688172": "燕东微"}


def log(msg):
    line = f"[{datetime.datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def wait_until(h, m):
    now = datetime.datetime.now()
    tgt = now.replace(hour=h, minute=m, second=10, microsecond=0)
    if tgt < now:
        return
    log(f"等待 {tgt:%H:%M} ...")
    time.sleep(max(0, (tgt - now).total_seconds()))


def main():
    log("尾盘值守启动")
    wait_until(14, 44)
    pos = _load()["positions"]
    codes = sorted(set(list(pos.keys())))
    plan_p = ROOT / "outputs" / "next_plan.csv"
    if plan_p.exists():
        for code, side, sh, px, nm in orderfile.read_plan(plan_p):
            if side == "buy" and code not in codes:
                codes.append(code)
    px = quotes.live_px(codes)
    log("实时价: " + " ".join(f"{k}={v}" for k, v in px.items()))
    sells = []
    for r in status(px):
        if "px" in r and r["action"].startswith("[!!]"):
            sells.append(("SELL", r["code"], r["shares"], r["px"], NAMES.get(r["code"], "")))
            log(f"卖出触发 {r['code']} {r['shares']}股@{r['px']:.2f} | {r['action']}")
    buys = []
    if plan_p.exists():
        sent = ROOT / "outputs" / "orders_sent.json"
        today = time.strftime("%Y%m%d")
        already = False
        if sent.exists():
            already = any(x.get("date") == today for x in json.load(open(sent, encoding="utf-8")))
        if not already:
            for code, side, sh, pxr, nm in orderfile.read_plan(plan_p):
                if side == "buy" and code in px:
                    buys.append(("BUY", code, sh, px[code], nm))
            log(f"发现买计划 {plan_p.name}, 买单 {len(buys)} 笔")
        else:
            log("今日已发过单, 跳过买单")
    broker = FileOrderBroker()
    if sells:
        broker.scan_dir.mkdir(parents=True, exist_ok=True)
        broker.place_batch(sells, make_fin=True)
        log(f"[自动] 已放卖单 {len(sells)} 笔")
    if buys:
        broker.place_batch(buys, make_fin=True)
        log(f"[自动] 已放买单 {len(buys)} 笔")
        sent = []
        p = ROOT / "outputs" / "orders_sent.json"
        if p.exists():
            sent = json.load(open(p, encoding="utf-8"))
        sent.append(dict(date=time.strftime("%Y%m%d"), src="tail_watch", rows=[o[0]+o[1] for o in buys]))
        json.dump(sent, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not sells and not buys:
        log("无卖出触发、无买计划 -> 今天不动作, 拿住")
    wait_until(15, 1)
    log("收盘值守结束")
    sys.exit(0)


if __name__ == "__main__":
    main()
