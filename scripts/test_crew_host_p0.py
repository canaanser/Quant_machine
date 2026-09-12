"""crew_host 门铃「老板优先（P0）」自测（老板 2026-09-13 定：老板的公告和门铃永远优先处理）。

跑法：python scripts/test_crew_host_p0.py
不联网、不投递、不碰真实信箱——`run_codex_wake` 被替换成桩函数，只验证判据与排序/限流。
"""
import contextlib
import datetime
import importlib.util
import io
import json
import os
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("crew_host_under_test", os.path.join(HERE, "crew_host.py"))
ch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ch)

FAILS = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "   -> " + str(extra)))
    if not cond:
        FAILS.append(name)


# ── ① 判据：什么算「老板优先」─────────────────────────────────────────────
check("老板本人发来的 → P0", ch.is_priority_row({"from": "老板", "body": "在吗"}))
check("【公告】正文 → P0", ch.is_priority_row({"from": "codex-看板编辑", "body": "【公告 N-XXXX】..."}))
check("（公告 N-xxxx 投递提示）→ P0", ch.is_priority_row({"from": "老板", "body": "（公告 N-ED4C 投递提示 · 来自 老板）"}))
check("（催办 · 公告 N-xxxx）**不算 P0**（机器人催办不许借老板的优先级）",
      not ch.is_priority_row({"from": "codex-看板服务", "body": "（催办 · 公告 N-2343）你还没回执。"}))
check("（公告投递提示）但发件人不是老板 → **不算 P0**",
      not ch.is_priority_row({"from": "codex-看板服务", "body": "（公告 N-ED4C 投递提示 · 来自 老板）"}))
check("普通线间来信 ≠ P0", not ch.is_priority_row({"from": "codex-套件", "body": "【回·补卡裁定收到，投影已备好】"}))
check("空记录 ≠ P0", not ch.is_priority_row({}))


# ── ② 排序与限流：造环境，真跑一遍 worker（投递换成桩）──────────────────────
def build(lines):
    """lines: [(看板名, slug, [信箱记录...])] → 临时 DIALOG 目录（含 agents.json）"""
    tmp = tempfile.mkdtemp(prefix="p0test-")
    agents = {}
    for name, slug, rows in lines:
        agents[name] = {"slug": slug, "threadId": "tid-" + slug, "level": "member"}
        with io.open(os.path.join(tmp, "pending_%s.ndjson" % slug), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with io.open(os.path.join(tmp, "agents.json"), "w", encoding="utf-8") as f:
        json.dump({"agents": agents}, f, ensure_ascii=False)
    return tmp


def run(tmp, state):
    """把宿主指到临时环境（**绝不碰真实名册/信箱/日志**），再跑一遍门铃小工。"""
    ch.DIALOG = tmp
    ch.AGENTS = os.path.join(tmp, "agents.json")
    ch.LOG = os.path.join(tmp, "crew_host_log.txt")
    ch.PUSHED_LEDGER = os.path.join(tmp, "pushed.ndjson")     # 共用记账（两条通道合一）
    ch.HUB_PUSHED = {}
    ch.HUB_PUSHED_CNT = {}
    ch.SESSIONS_DIR = os.path.join(tmp, "sessions")           # 会话账本目录（判"它动过没有"）
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ch.worker_doorbell_queue(state, False, None)
    text = out.getvalue()
    order = []
    for line in text.split("\n"):
        # 普通轮 & 兜底轮都算（兜底那行是 `doorbell-queue[兜底] → …`）
        if "doorbell-queue" in line and "→ " in line and "：" in line:
            order.append(line.split("→ ")[1].split(" ")[0])
    return order, text


ch.find_codex_exe = lambda: "fake-codex"          # 只过"找得到 exe"这道早退
ch.run_codex_wake = lambda exe, tid, msg: (0, "stub", "stub")   # 不真投递
ch.read_last_spoken = lambda cfg: {}              # 所有人"没发过言"→ 信箱全算未读

P0_A = {"ts": "2026-09-13 03:00", "from": "老板", "body": "【公告 N-TEST】先停一下"}
# 第二条 P0 用"**非老板发的真公告**"（P0 判据收窄后：催办不再算 P0，但真公告仍算 —— 2026-09-13 07:4x）
P0_B = {"ts": "2026-09-13 03:01", "from": "codex-看板编辑", "body": "【公告 N-TEST2】制度更新：请照办"}
NORM = {"ts": "2026-09-13 04:00", "from": "codex-套件", "body": "【回·裁定收到】"}

# 场景 1：2 条 P0 + 3 条普通（普通单轮上限 2）→ P0 两条都要响，且排最前
tmp = build([
    ("线普通1", "s-n1", [NORM]), ("线普通2", "s-n2", [NORM]), ("线普通3", "s-n3", [NORM]),
    ("线P0甲", "s-p1", [P0_A]), ("线P0乙", "s-p2", [P0_B]),
])
state = {}
order, text = run(tmp, state)
check("场景1：P0 两条排在最前", order[:2] in (["s-p1", "s-p2"], ["s-p2", "s-p1"]), order)
check("场景1：P0 两条都被敲（不吃普通单轮 2 条的上限）", "s-p1" in order and "s-p2" in order, order)
check("场景1：普通线被单轮上限压到 2 条", len([s for s in order if s.startswith("s-n")]) == ch.MAX_RING_PER_RUN, order)
check("场景1：P0 铃在日志里标 [P0]", "[P0]" in text, text[:200])
check("场景1：每条线只敲一次（P0 不被普通轮重复敲）", len(order) == len(set(order)), order)
check("场景1：门铃日志带**级别字段**（级别一变，日志自己会变）", "lvl=member" in text, text[:200])

# 场景 2：同一状态再跑一遍 → P0 处于 120 秒冷却，不该被连敲
order2, _ = run(tmp, state)
check("场景2：P0 冷却期内不重复敲", "s-p1" not in order2 and "s-p2" not in order2, order2)

# 场景 3：8 条 P0 → 单轮 P0 上限 6
tmp3 = build([("线P%d" % i, "p%d" % i, [P0_A]) for i in range(8)])
order3, text3 = run(tmp3, {})
check("场景3：P0 单轮上限生效（<= %d）" % ch.P0_MAX_RING_PER_RUN, len(order3) <= ch.P0_MAX_RING_PER_RUN, order3)
check("场景3：超限时打出「下一轮再敲」而不是静默丢弃", "本轮已达 P0 上限" in text3)

# 场景 4：回滚开关 `P0_ENABLED=False` → 退回旧行为（P0 不再插队、也不再带优先标记）
tmp4 = build([
    ("线普通1", "s-n1", [NORM]), ("线普通2", "s-n2", [NORM]), ("线普通3", "s-n3", [NORM]),
    ("线P0甲", "s-p1", [P0_A]),
])
ch.P0_ENABLED = False
order4, text4 = run(tmp4, {})
ch.P0_ENABLED = True                       # 复原，别影响后面
check("场景4（回滚开关）：P0 不再插队（按名册顺序走普通轮）", order4[:2] == ["s-n1", "s-n2"], order4)
check("场景4（回滚开关）：不再出现【老板·优先】标记", "【老板·优先" not in text4)

# ── ③ 组员不发言（老板 2026-09-13 定）→ 同一封信只推一次 ──────────────────────
def ts_ago(mins):
    return (datetime.datetime.now() - datetime.timedelta(minutes=mins)).strftime("%Y-%m-%d %H:%M")


tmp5 = build([("组员甲", "s-mem", [{"ts": ts_ago(70), "from": "codex-套件", "body": "普通派活"}])])
st5 = {}
o5a, _ = run(tmp5, st5)
check("场景5：第一次推给组员", o5a == ["s-mem"], o5a)
# 把"上次推送时刻"伪造成一小时前 —— 冷却(600s)已过，此时若还重复推，就说明是水位没生效
st5["queuedAt"]["s-mem"] = time.time() - 3600
o5b, _ = run(tmp5, st5)
check("场景5：同一封信不再重复推（是靠**水位**挡的，不是靠冷却）", o5b == [], o5b)

# 场景 6：来了新信 → 再推一次，且只数新信
with io.open(os.path.join(tmp5, "pending_s-mem.ndjson"), "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": ts_ago(0), "from": "codex-套件", "body": "第二封"}, ensure_ascii=False) + "\n")
o5c, t5c = run(tmp5, st5)
check("场景6：新信到达 → 再推一次", o5c == ["s-mem"], o5c)
check("场景6：只数新信（日志里 n=1，不是 2）", "n=1 " in t5c, t5c[-200:])

# 场景 7：投递失败 → 不抬水位 → 下次还会重试（"叫不醒"仍能被发现）
tmp7 = build([("组员乙", "s-fail", [{"ts": ts_ago(5), "from": "codex-套件", "body": "派活"}])])
st7 = {}
ch.run_codex_wake = lambda exe, tid, msg: (1, "boom", "stub")
o7a, _ = run(tmp7, st7)
ch.run_codex_wake = lambda exe, tid, msg: (0, "stub", "stub")
o7b, _ = run(tmp7, st7)
check("场景7：投递失败时不抬水位（下一轮仍会推）", o7b == ["s-fail"], (o7a, o7b))

# ── ④ 两条通道合一 + 慢速兜底（老板 2026-09-13 04:5x：「按可靠的方式改一下」）──
# 场景 8：Hub 已推成功（记了账）→ 门铃**不再重复叫**同一封
tmp8 = build([("组员丙", "s-hub", [{"ts": ts_ago(3), "from": "codex-套件", "body": "派活"}])])
with io.open(os.path.join(tmp8, "pushed.ndjson"), "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": ts_ago(2), "ts_ms": int(time.time() * 1000), "by": "hub",
                        "to": "s-hub", "mailbox_ts": ts_ago(3)}, ensure_ascii=False) + "\n")
o8, _ = run(tmp8, {})
check("场景8：Hub 推过（有记账）→ 门铃不再叫同一封", o8 == [], o8)

# 场景 9：账本里没有它（推送失败/没推）→ 门铃**照叫**（这就是兜底）
o9, _ = run(build([("组员丁", "s-nohub", [{"ts": ts_ago(3), "from": "codex-套件", "body": "派活"}])]), {})
check("场景9：没有推送记账 → 门铃照叫（兜底有效）", o9 == ["s-nohub"], o9)

# 场景 10：首触后本人一直没动作 → 30 分钟兜一次；有动作就不兜
tmp10 = build([("组员戊", "s-poke", [{"ts": ts_ago(40), "from": "codex-套件", "body": "派活"}])])
st10 = {}
o10a, _ = run(tmp10, st10)
st10["poked"]["s-poke"]["lastAt"] -= 31 * 60 * 1000          # 假装首触已过 31 分钟
o10b, t10b = run(tmp10, st10)
check("场景10：31 分钟无动作 → 兜一次（日志标 [兜底]）", o10b == ["s-poke"] and "[兜底]" in t10b, (o10a, o10b))
# 本人投过一封信（组员不上板，投信也算"有动作"）→ 不再兜
with io.open(os.path.join(tmp10, "pending_s-组外.ndjson"), "w", encoding="utf-8") as f:
    f.write(json.dumps({"ts": ts_ago(1), "from": "组员戊", "to": "codex-看板编辑", "body": "回话"}, ensure_ascii=False) + "\n")
st10["poked"]["s-poke"]["lastAt"] = int(time.time() * 1000) - 3 * 3600 * 1000
o10c, _ = run(tmp10, st10)
check("场景10：本人投过信 → 视为已动作，不再兜", o10c == [], o10c)

# 场景 11：**老状态迁移**——`attempts` 里记着"上次推过的那封信"，新水位字段还没写时不许再叫一次
_old_ts = ts_ago(20)
tmp11 = build([("组员己", "s-mig", [{"ts": _old_ts, "from": "codex-套件", "body": "派活"}])])
st11 = {"attempts": {"s-mig": [_old_ts, 1]}}          # 老状态：推过一次，但还没有 pushedWm
o11, _ = run(tmp11, st11)
check("场景11：老状态迁移后不再重复叫（跨版本上线不补叫）", o11 == [], o11)
check("场景11：迁移确实写进了 pushedWm", int((st11.get("pushedWm") or {}).get("s-mig", 0)) > 0, st11.get("pushedWm"))

# ── ⑤ 看板编辑 05:20 提的两点（我核对后采纳，落到读取侧）──────────────────────
# 场景 12：同一分钟两封**不同**的信，只推过一封 → 另一封**仍然是未读**（不许被吞）
_same_min = ts_ago(6)
tmp12 = build([("组员庚", "s-min", [
    {"ts": _same_min, "from": "codex-套件", "body": "第一封"},
    {"ts": _same_min, "from": "codex-人事", "body": "第二封"},
])])
with io.open(os.path.join(tmp12, "pushed.ndjson"), "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": ts_ago(5), "ts_ms": int(time.time() * 1000), "by": "hub",
                        "to": "s-min", "mailbox_ts": _same_min}, ensure_ascii=False) + "\n")
o12, t12 = run(tmp12, {})
check("场景12：同分钟只推过一封 → 另一封仍被叫", o12 == ["s-min"], o12)
check("场景12：而且只报 1 条（日志 n=1，不是 2）", "n=1 " in t12, t12[-160:])

# 场景 13：`mailbox_ts` 为空的记账行**不许抬水位**（否则会吞掉同一分钟的真信）
tmp13 = build([("组员辛", "s-empty", [{"ts": ts_ago(6), "from": "codex-套件", "body": "真信"}])])
with io.open(os.path.join(tmp13, "pushed.ndjson"), "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": ts_ago(5), "ts_ms": int(time.time() * 1000), "by": "hub",
                        "to": "s-empty", "mailbox_ts": ""}, ensure_ascii=False) + "\n")
o13, _ = run(tmp13, {})
check("场景13：mailbox_ts 为空的记账行不抬水位（真信照叫）", o13 == ["s-empty"], o13)

# 场景 14：账本被"另写新文件 + 替换"的瞬间读到 0 行 → **沿用上次水位**，不许当成归零全员重叫
tmp14 = build([("组员壬", "s-ledger", [{"ts": ts_ago(4), "from": "codex-套件", "body": "派活"}])])
_led = os.path.join(tmp14, "pushed.ndjson")
with io.open(_led, "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": ts_ago(3), "ts_ms": int(time.time() * 1000), "by": "hub",
                        "to": "s-ledger", "mailbox_ts": ts_ago(4)}, ensure_ascii=False) + "\n")
st14 = {}
o14a, _ = run(tmp14, st14)
check("场景14：账本有记录时正常（不该叫）", o14a == [], o14a)
os.remove(_led)                      # 模拟"替换瞬间文件不在"
o14b, _ = run(tmp14, st14)
check("场景14：账本瞬间缺失 → 沿用上次水位（不许全员重叫）", o14b == [], o14b)

# 场景 15：**键空间归一**——Hub 账本行写的是**看板名**，小工用 slug 查也必须匹配上（不许再各推一次）
tmp15 = build([("组员癸", "s-keyspace", [{"ts": ts_ago(4), "from": "codex-套件", "body": "派活"}])])
with io.open(os.path.join(tmp15, "pushed.ndjson"), "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": ts_ago(3), "ts_ms": int(time.time() * 1000), "by": "hub",
                        "to": "组员癸", "mailbox_ts": ts_ago(4)}, ensure_ascii=False) + "\n")
o15, _ = run(tmp15, {})
check("场景15：Hub 写看板名 → 小工（slug）也认账，不再各推一次", o15 == [], o15)

# 场景 16：**只在对话框里回话**也算"有动作" → 不许再被慢速兜底追（量化总监 05:54 报的假阳性）
tmp16 = build([("组员子", "s-sess", [{"ts": ts_ago(40), "from": "codex-套件", "body": "派活"}])])
st16 = {}
run(tmp16, st16)                                   # 首触
sd = os.path.join(tmp16, "sessions", "2026", "09", "13")
os.makedirs(sd, exist_ok=True)
with io.open(os.path.join(sd, "rollout-2026-09-13T05-00-00-tid-s-sess.jsonl"), "w", encoding="utf-8") as f:
    f.write("{}")
st16["poked"]["s-sess"]["lastAt"] -= 31 * 60 * 1000     # 假装首触已过 31 分钟
o16, _ = run(tmp16, st16)
check("场景16：会话里刚起过回合 → 不再兜底（不追已处理的线）", o16 == [], o16)

print("\n结果：" + ("全部通过" if not FAILS else "失败 %d 项 -> %s" % (len(FAILS), FAILS)))
raise SystemExit(1 if FAILS else 0)
