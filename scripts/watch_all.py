# -*- coding: utf-8 -*-
"""全天值守 v2 (watch_all) 2026-09-09 — 9:20~15:05 全程在岗
职责(执行层, 不分层之外的事):
  盘中 9:30-14:40 : 每60s拉持仓实时价, 距防崩3%内/急跌→警告日志+心跳文件
  14:44 执行段   : 卖出触发(防崩/峰顶/滞涨)→自动放卖单; 有next_plan→自动放买单(当日防重)
  15:02          : sync_fills 回账 → 写当日值守报告 → 退出
守护: 心跳 outputs/watch_heartbeat.txt 每轮更新; 异常捕获不静默死
用法(手动):  python -B scripts/watch_all.py
   --dry  只演练执行段逻辑(不下单不等待), 便于验证
"""
import io, json, os, sys, time, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    if sys.stdout is not None and getattr(sys.stdout, "buffer", None) is not None:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass
from core.trade.ledger import _load, status
from core.trade.file_order_broker import FileOrderBroker
from core.lib import orderfile, quotes

ROOT = Path(__file__).parent.parent
HEART = ROOT / "outputs" / "watch_heartbeat.txt"
LOG = ROOT / "outputs" / "watch_all_log.txt"
NAMES = {"603256": "宏和科技", "301358": "湖南裕能", "002595": "豪迈科技",
         "688775": "影石创新", "688702": "盛科通信-U", "688172": "燕东微"}
DRY = "--dry" in sys.argv


def log(msg, echo=True):
    line = f"[{datetime.datetime.now():%H:%M:%S}] {msg}"
    if echo:
        try:  # pythonw 无控制台时 sys.stdout 为 None, 不能崩
            print(line, flush=True)
        except Exception:
            pass
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def hb(state):
    try:
        HEART.write_text(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} state={state}", encoding="utf-8")
    except Exception:
        pass


_GUARD_F = None


def take_guard():
    """单实例锁: 计划任务9:20 与 看门狗(9:15起见心跳过期即拉) 可能同时拉起本进程,
    两实例都会在14:44执行放单 -> 会重复下单(卖单无防重)。锁防双跑。
    持锁至进程退出; 进程崩溃OS自动释放, 无僵锁。"""
    global _GUARD_F
    try:
        import msvcrt
        p = ROOT / "outputs" / "resident.lock"
        f = open(p, "w")
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        f.write(str(os.getpid()))
        f.flush()
        _GUARD_F = f
        return True
    except OSError:
        try:
            log("已有值守进程在跑(resident.lock), 本实例退出")
        except Exception:
            pass
        return False
    except Exception:
        return True   # 非常规环境(如无msvcrt)不阻断


def release_guard():
    global _GUARD_F
    if _GUARD_F:
        try:
            _GUARD_F.close()
        except Exception:
            pass
        _GUARD_F = None


def now_min():
    return datetime.datetime.now().hour * 60 + datetime.datetime.now().minute


def fetch_px(codes):
    for k in range(4):
        try:
            return quotes.live_px(codes)
        except Exception as e:
            log(f"取价失败重试{k+1}: {repr(e)[:80]}")
            time.sleep(3)
    return {}


def execute_phase():
    """14:44 执行: 卖自动/买按计划"""
    pos = _load()["positions"]
    codes = sorted(set(list(pos.keys())))
    plan_p = ROOT / "outputs" / "next_plan.csv"
    if plan_p.exists():
        for code, side, sh, pxr, nm in orderfile.read_plan(plan_p):
            if side == "buy" and code not in codes:
                codes.append(code)
    px = fetch_px(codes)
    log("执行段 实时价: " + " ".join(f"{k}={v}" for k, v in px.items()))
    if not px:
        log("执行段取价全失败 -> 本日不动作(防误单), 收盘再查")
        return
    sells, buys = [], []
    for r in status(px):
        if "px" in r and r["action"].startswith("[!!]"):
            sells.append(("SELL", r["code"], r["shares"], r["px"], NAMES.get(r["code"], "")))
            log(f"卖出触发 {r['code']} {r['shares']}股@{r['px']:.2f} | {r['action']}")
    if plan_p.exists() and not DRY:
        sent_p = ROOT / "outputs" / "orders_sent.json"
        today = time.strftime("%Y%m%d")
        already = sent_p.exists() and any(x.get("date") == today
                                         for x in json.load(open(sent_p, encoding="utf-8")))
        if not already:
            for code, side, sh, pxr, nm in orderfile.read_plan(plan_p):
                if side == "buy" and code in px:
                    buys.append(("BUY", code, sh, px[code], nm))
            log(f"买计划 {plan_p.name} -> 买单 {len(buys)} 笔")
        else:
            log("今日已发单, 跳过买单")
    if DRY:
        log(f"[dry] 本应放: 卖{len(sells)} 买{len(buys)} -> 演练不真放")
        return
    broker = FileOrderBroker()
    if sells:
        broker.place_batch(sells, make_fin=True)
        log(f"[自动] 已放卖单 {len(sells)} 笔")
    if buys:
        broker.place_batch(buys, make_fin=True)
        log(f"[自动] 已放买单 {len(buys)} 笔")
        sent = []
        p = ROOT / "outputs" / "orders_sent.json"
        if p.exists():
            sent = json.load(open(p, encoding="utf-8"))
        sent.append(dict(date=time.strftime("%Y%m%d"), src="watch_all", rows=[o[0] + o[1] for o in buys]))
        json.dump(sent, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not sells and not buys:
        log("无卖出触发、无买计划 -> 执行段不动作, 拿住")


def main():
    log("全天值守 v2 启动" + ("(dry演练)" if DRY else ""))
    hb("start")
    if not DRY and not take_guard():
        return  # 已有值守实例在跑
    try:
        if DRY:
            execute_phase()
            hb("dry_done")
            return
        # 盘中监控 9:30~14:40
        last_warn = 0
        while now_min() < 14 * 60 + 40:
            m = now_min()
            if 9 * 60 + 30 <= m:
                pos = _load()["positions"]
                codes = list(pos.keys())
                px = fetch_px(codes)
                if px:
                    lines = []
                    for c in codes:
                        p = px.get(c)
                        if not p:
                            continue
                        fang = pos[c]["cost"] * 0.88
                        near = p <= fang * 1.03
                        lines.append(f"{c}={p:.2f}")
                        if near and m - last_warn >= 5:
                            log(f"⚠ {NAMES.get(c, c)} 现价{p:.2f} 逼近防崩{fang:.2f}({p/fang-1:+.1%})")
                            last_warn = m
                    hb("watch|" + " ".join(lines))
                else:
                    hb("watch|noquote")
                time.sleep(60)
            else:
                time.sleep(30)
        # 执行段
        execute_phase()
        hb("exec_done")
        # 等收盘后回账
        while now_min() < 15 * 60 + 1:
            time.sleep(20)
        time.sleep(90)
        try:
            n = FileOrderBroker().sync_fills()
            log(f"收盘回账: 新增{n}笔")
        except Exception as e:
            log(f"收盘回账失败 {repr(e)[:100]}")
        hb("closed")
        log("全天值守结束")
        release_guard()
    except Exception as e:
        log(f"[异常] {e}")
        hb("error")
        release_guard()


if __name__ == "__main__":
    main()
