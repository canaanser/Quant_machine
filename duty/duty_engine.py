# -*- coding: utf-8 -*-
"""duty_engine — 值守调度引擎(2026-09-09 定稿: 内核六块, 稳健优先)
定位: 装"任务插件"的主体=值班人员; 只调 self_api(量化系统对外的API)。
六块: ①心跳调度循环 ②任务注册表 ③出勤表(schedule.yaml) ④交易时段状态机
      ⑤盯市(取价/心跳/逼近防崩预警) ⑥状态持久化+幂等+决策留痕
健壮性: 每tick/任务 try-except 不中断; 取价失败重试; 状态文件落盘;
        重启同一天不重复执行 once 任务; 每步决策写日志。
用法:  python -B duty/duty_engine.py         常驻(正常跑)
      python -B duty/duty_engine.py --selftest  一回合自检(不真动)
"""
import io, json, sys, time, datetime, traceback
from pathlib import Path

ROOT = Path(__file__).parent.parent
for p in (str(ROOT), str(ROOT / "duty")):
    if p not in sys.path:
        sys.path.insert(0, p)
# stdout 可能是无效句柄/None(pythonw、被无控制台父进程Popen) -> 防启动即崩
try:
    if sys.stdout is not None and getattr(sys.stdout, "buffer", None) is not None:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

import yaml
import self_api as api

SELFTEST = "--selftest" in sys.argv
SHADOW = ("--shadow" in sys.argv) or ("--dryexec" in sys.argv)   # 演练: 只算+留痕, 不放真单
RETIRE = "--retire" in sys.argv  # 一次性值守: 收盘(15:45)自动退岗; 默认=常驻(stockdb式, 永不退岗)
LOG = ROOT / "outputs"
# shadow(观摩)模式心跳写独立文件: 主值守watch_all的心跳不被观摩进程掩盖,
# 否则主进程死掉时看门狗会因为观摩心跳还在而永不拉起真值守
HEART = (LOG / "watch_heartbeat_shadow.txt") if SHADOW else (LOG / "watch_heartbeat.txt")
STATE = LOG / "duty_state.json"
DECI = LOG / "duty_decisions.log"

NAMED = {"603256": "宏和科技", "301358": "湖南裕能", "002595": "豪迈科技",
         "688775": "影石创新", "688702": "盛科通信-U", "688172": "燕东微"}

_GUARD_F = None


def take_guard():
    """单实例锁(与watch_all共用 outputs/resident.lock):
    计划任务09:20 与 看门狗(9:15起心跳过期即拉) 会同时拉起值守 -> 双实例14:44重复放单。
    持锁至进程退出; 进程崩溃OS自动释放, 无僵锁。shadow/selftest 不占锁。"""
    global _GUARD_F
    try:
        import msvcrt
        f = open(LOG / "resident.lock", "w")
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        f.write(str(now().timestamp()))
        f.flush()
        _GUARD_F = f
        return True
    except OSError:
        log("已有值守进程在跑(resident.lock), 本实例退出")
        return False
    except Exception:
        return True


def release_guard():
    global _GUARD_F
    if _GUARD_F:
        try:
            _GUARD_F.close()
        except Exception:
            pass
        _GUARD_F = None


def now():
    return datetime.datetime.now()


def hm(dt=None):
    dt = dt or now()
    return dt.hour * 60 + dt.minute


def H(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def log(msg, echo=True):
    line = f"[{now():%Y-%m-%d %H:%M:%S}] {msg}"
    if echo:
        try:  # pythonw 无控制台时 sys.stdout 为 None, 不能崩
            print(line, flush=True)
        except Exception:
            pass
    try:
        with open(LOG / "duty_log.txt", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def decision(msg):
    try:
        with open(DECI, "a", encoding="utf-8") as f:
            f.write(f"[{now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


def hb(state):
    try:
        HEART.write_text(f"{now():%Y-%m-%d %H:%M:%S} state={state}", encoding="utf-8")
    except Exception:
        pass


# ---------------- 调度器 ----------------
class DutyEngine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.tasks = {}          # name -> dict(fn, freq_sec, window_bounds, once, at)
        self.state = self._load_state()
        self.day = now().strftime("%Y%m%d")

    def _load_state(self):
        try:
            d = json.load(open(STATE, encoding="utf-8"))
            if d.get("date") != now().strftime("%Y%m%d"):
                d = {"date": now().strftime("%Y%m%d"), "done": {}}
            return d
        except Exception:
            return {"date": now().strftime("%Y%m%d"), "done": {}}

    def _save_state(self):
        try:
            json.dump(self.state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass

    def reg(self, name, fn, freq_sec=None, window=None, at=None, once=False, enabled=True):
        """注册任务(插件位): 普通函数, 调 self_api"""
        self.tasks[name] = dict(fn=fn, freq=freq_sec, at=(H(at) if at else None),
                                once=once, enabled=enabled,
                                win=[(H(a), H(b)) for seg in (window or "").split(",")
                                     for a, b in [seg.split("-")]] if window else None,
                                last=0)

    def session(self):
        """交易时段名"""
        if now().weekday() > 4:
            return "周末"
        m = hm()
        s = self.cfg["session"]
        if m < H(s["pre"]):
            return "盘前"
        if m < H(s["open"]):
            return "待开"
        if m < H(s["lunch"]):
            return "上午盘"
        if m < H(s["afternoon"]):
            return "午休"
        if m < H(s["tail"]):
            return "下午盘"
        if m < H(s["close"]):
            return "尾盘窗"
        if m < H(s["post"]):
            return "收盘"
        return "盘后"

    def _due(self, name, t):
        t = self.tasks[name]
        if not t["enabled"]:
            return False
        if now().weekday() > 4 or now().strftime("%Y-%m-%d") in self.cfg["market"].get("off_days", []):
            return False
        if t["at"] is not None:            # 定点一次(仅当日内执行窗)
            if t["once"] and name in self.state["done"]:
                return False
            if hm() > 15 * 60 + 59:        # 收盘后不再补跑定点任务
                return False
            return hm() >= t["at"]
        # 周期任务窗口
        w = t["win"]
        if w and not any(a <= hm() <= b for a, b in w):
            return False
        if t["freq"] and now().timestamp() - t["last"] < t["freq"]:
            return False
        return True

    def tick(self):
        # 跨日自愈: 万一实例跨天存活(如--stay忘关), 次日零点起 once 任务要能重触发
        today = now().strftime("%Y%m%d")
        if self.state.get("date") != today:
            self.state = {"date": today, "done": {}}
            self._save_state()
            log(f"跨日重置状态 -> {today} (done清空, once任务今日可重触发)")
        sess = self.session()
        hb(f"duty|{sess}|tasks={len(self.tasks)}")
        for name in list(self.tasks):
            t = self.tasks[name]
            try:
                if not self._due(name, now()):
                    continue
                decision(f"[task:{name}] 触发 session={sess}")
                t["fn"]()
                if t["at"] is not None and t["once"]:
                    self.state["done"][name] = now().strftime("%H:%M:%S")
                    self._save_state()
                    log(f"once任务 {name} 完成并记档")
            except Exception as e:
                log(f"[task:{name}] 异常: {e} :: {traceback.format_exc(limit=2)}")
        time.sleep(1)


# ---------------- 任务实现(值班员=编排, 逻辑走 api) ----------------
def task_heartbeat():
    pass  # tick 已负责心跳


def task_monitor():
    """盯市: 取持仓实时价, 逼近防崩预警, 低频状态留痕"""
    pos = api.positions()
    codes = list(pos.keys())
    px = _px_retry(codes)
    if not px:
        return
    msgs = []
    warn = []
    for c in codes:
        p = px.get(c)
        if not p:
            continue
        cost = pos[c]["cost"]
        fb = cost * 0.88
        msgs.append(f"{c}={p:.2f}")
        if p <= fb * self_api_cfg_near():
            warn.append(f"{NAMED.get(c, c)} 现价{p:.2f} 逼近防崩{fb:.2f}({(p/fb-1):+.1%})")
    hb("mon|" + " ".join(msgs))
    for w in warn:
        log("⚠ " + w)
        decision(f"[monitor] ⚠ {w}")


def _read_plan():
    """读取 outputs/next_plan.csv -> [(code, side, shares, price, name)]; 无文件返回[]"""
    import csv
    plan_p = ROOT / "outputs" / "next_plan.csv"
    out = []
    if not plan_p.exists():
        return out
    for ln in csv.reader(open(plan_p, encoding="utf-8-sig")):
        if not ln or not ln[0].strip() or ln[0].strip().lower() == "code":
            continue
        code, side, shares, price, name = (ln + [""] * 5)[:5]
        out.append((code, side, int(float(shares)), price, name))
    return out


def _already_sent():
    p = ROOT / "outputs" / "orders_sent.json"
    try:
        if p.exists() and any(x.get("date") == now().strftime("%Y%m%d")
                              for x in json.load(open(p, encoding="utf-8"))):
            return True
    except Exception:
        pass
    return False


def task_tail_exec():
    """14:44 执行段: ①卖出触发(防崩/峰顶/滞涨)自动放 ②next_plan 减仓行(sell)自动放
    ③next_plan 买入行(buy)自动放买。当日防重。取价覆盖 持仓+计划码。"""
    plan = _read_plan()
    pos = api.positions()
    codes = list(pos.keys())
    for (code, side, sh, pxr, nm) in plan:
        if code not in codes:
            codes.append(code)
    px = _px_retry(codes)
    if not px:
        log("执行段取价失败 -> 本日不动作")
        return
    # 1) 卖出触发(规则)
    ev = api.evaluate_holdings(px)
    sells = []
    for e in ev:
        if e["trigger"] in ("防崩", "峰顶", "滞涨") and e.get("px"):
            sells.append([e["code"], e["shares"], e["px"],
                          e["name"] or NAMED.get(e["code"], "")])
            decision(f"[tail] 卖触发 {e['code']} {e['action']}")
    # 2) 计划减仓(sell行): 不超持仓; 同码已触发卖出则跳过(防重复卖超)
    if plan and not _already_sent():
        for (code, side, sh, pxr, nm) in plan:
            if side == "sell" and code in pos and code in px:
                if any(s[0] == code for s in sells):
                    decision(f"[tail] {code} 已触发卖出, 跳过计划减仓")
                    continue
                own = pos[code]["shares"]
                if own <= 0:
                    continue
                sells.append([code, min(int(sh), own), px[code], nm or NAMED.get(code, "")])
                decision(f"[tail] 计划减仓 {code} {min(int(sh), own)}股")
    # 3) 买入(按计划)
    buys = []
    if plan and not _already_sent():
        for (code, side, sh, pxr, nm) in plan:
            if side == "buy" and code in px:
                buys.append(("BUY", code, sh, px[code], nm or NAMED.get(code, "")))
        decision(f"[tail] 买计划 {len(buys)} 笔")
    sells_t = [tuple(s) for s in sells]
    if not sells_t and not buys:
        decision("[tail] 无卖出触发、无计划 -> 不动")
    if SHADOW:
        log(f"[shadow] 本应放: 卖{len(sells_t)} 买{len(buys)} -> 演练不真放")
        return
    if sells_t:
        api.dispatch(sells_t)
        log(f"[执行] 已放卖单 {len(sells_t)}")
    if buys:
        api.dispatch(buys)
        _mark_sent(sells_t + buys)
        log(f"[执行] 已放买单 {len(buys)}")


def task_close_sync():
    if SHADOW:
        decision("[close] shadow 模式跳过回账(主进程watch_all负责)")
        return
    try:
        n = api.sync_fills()
        log(f"[收盘] 回账新增 {n} 笔")
        decision(f"[close] sync_fills n={n}")
    except Exception as e:
        log(f"[收盘] 回账异常 {e}")


def _px_retry(codes):
    for k in range(4):
        try:
            return api.market_px(codes)
        except Exception as e:
            log(f"取价重试{k + 1}: {e}")
            time.sleep(3)
    return {}


def self_api_cfg_near():
    try:
        return float(ENGINE_CFG["tasks"]["monitor"].get("near_fangbeng", 1.03))
    except Exception:
        return 1.03


def _mark_sent(rows):
    p = ROOT / "outputs" / "orders_sent.json"
    sent = []
    if p.exists():
        sent = json.load(open(p, encoding="utf-8"))
    sent.append(dict(date=now().strftime("%Y%m%d"), src="duty_engine",
                     rows=[o[0] + o[1] for o in rows]))
    json.dump(sent, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


ENGINE_CFG = None


def load_cfg():
    try:
        with open(ROOT / "duty" / "schedule.yaml", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return {}


def main():
    global ENGINE_CFG
    ENGINE_CFG = load_cfg()
    eng = DutyEngine(ENGINE_CFG)
    t = ENGINE_CFG.get("tasks", {})
    eng.reg("heartbeat", task_heartbeat, freq_sec=20)
    eng.reg("monitor", task_monitor,
            freq_sec=t.get("monitor", {}).get("freq_sec", 60),
            window=t.get("monitor", {}).get("window"),
            enabled=t.get("monitor", {}).get("enabled", True))
    eng.reg("tail_exec", task_tail_exec,
            at=t.get("tail_exec", {}).get("at_time", "14:44"),
            once=t.get("tail_exec", {}).get("once", True),
            enabled=t.get("tail_exec", {}).get("enabled", True))
    eng.reg("close_sync", task_close_sync,
            at=t.get("close_sync", {}).get("at_time", "15:05"),
            once=t.get("close_sync", {}).get("once", True),
            enabled=t.get("close_sync", {}).get("enabled", True))
    if SELFTEST:
        log("selftest: 一回合")
        eng.tick()
        log(f"selftest ok: session={eng.session()} done={eng.state['done']}")
        return
    if "--dryexec" in sys.argv:
        # 晚间演练: 不 due 也按当前持仓+next_plan 跑一次执行段(不真放单)
        log("dryexec: 晚间演练执行段(不真放单)")
        task_tail_exec()
        return
    if not SHADOW and not take_guard():
        return  # 已有值守实例在跑
    log(f"duty_engine 上岗 (session={eng.session()}"
        + (" shadow观摩" if SHADOW else "") + (" 收盘退岗模式" if RETIRE else " 常驻模式(stockdb式)") + ")")
    decision("duty_engine 启动" + (" [shadow]" if SHADOW else "") + (" [retire]" if RETIRE else " [常驻]"))
    hb("start")
    retire_hm = 15 * 60 + 45  # 仅 --retire 模式生效; schedule.yaml market.retire 可改
    try:
        retire_hm = H(ENGINE_CFG.get("market", {}).get("retire", "15:45"))
    except Exception:
        pass
    try:
        while True:
            # --retire 一次性模式: 收盘(15:45, 过看门狗窗口15:35)退岗; 默认常驻24h不退出
            if RETIRE and eng.session() == "盘后" and hm() >= retire_hm:
                log(f"收盘后退岗(>= {retire_hm // 60}:{retire_hm % 60:02d}), 明日计划任务再拉起")
                eng._save_state()
                release_guard()
                return
            eng.tick()
    except KeyboardInterrupt:
        log("值守手动退出")
        eng._save_state()
        release_guard()
    except Exception as e:
        log(f"[致命] {e} :: {traceback.format_exc(limit=3)}")
        eng._save_state()
        release_guard()
        raise


if __name__ == "__main__":
    main()
