#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""crew_host —— 沙箱外小工宿主（PLT-002）

为什么要有它：从 agent 沙箱里连宿主/平台会被告警拦（os error 10013），
所以凡是要"碰宿主"的搬运活，都必须跑在**沙箱外**（计划任务 / 管理员上下文）。

设计原则：
  - **只搬运，不决策**：不代替任何线"同意/批准/派单"；
  - **不碰引擎 / 托盘 / stockdb**（9/10 事故根因，写死在禁区里）；
  - 每个小工**独立开关 + dry-run**；幂等（游标在 state 里）；
  - 一切动作写日志，可审计。

小工（v1）：
  mirror-mailbox  把各线信箱里"还没被它处理"的留言，镜像到它工位的 .private/<slug>/inbox.md
  heartbeat       写心跳，让"小工还活着"看得见

用法：
  python scripts/crew_host.py --once --dry-run        # 只打印将要做什么，不写任何东西
  python scripts/crew_host.py --once                  # 跑一遍就退出（推荐给计划任务）
  python scripts/crew_host.py --interval 60           # 常驻：每 60 秒跑一遍
  python scripts/crew_host.py --only mirror-mailbox   # 只跑某个小工
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIALOG = os.path.join(ROOT, "outputs", "dialog")
OUT = os.path.join(ROOT, "outputs")
AGENTS = os.path.join(DIALOG, "agents.json")
STATE = os.path.join(OUT, "crew_host_state.json")
LOG = os.path.join(OUT, "crew_host_log.txt")
HEARTBEAT = os.path.join(OUT, "crew_host_heartbeat.txt")

def log(msg, dry=False):
    line = "[%s]%s %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), " [DRY]" if dry else "", msg)
    print(line, flush=True)
    if not dry:
        try:
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj, dry=False):
    if dry:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def ts_key(s):
    """把两种时间格式统一成可比较的键；解析不出来就退回原字符串。"""
    s = str(s or "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s[:19], fmt).timestamp()
        except Exception:
            continue
    return s


def read_ndjson(path):
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    rows.append({"_raw": line})
    except Exception:
        pass
    return rows


DIALOG_SRC = os.path.join(DIALOG, "dialog.ndjson")


def ts_ms(s):
    """宽容解析时间戳（看板真源是 ISO 带时区，信箱是 'YYYY-MM-DD HH:MM'）。"""
    s = str(s or "").strip().replace("T", " ")
    if not s:
        return 0
    s = s[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return int(datetime.strptime(s, fmt).timestamp() * 1000)
        except Exception:
            continue
    return 0


def read_last_spoken(cfg):
    """每条线在看板真源里**最后一次本人发言**的时间（slug -> ms）。

    ★ "只叫真未读"的依据（2026-09-12 二次落地——第一次加过又被整份改写吃掉）：
      信箱是 append-only 流水、没有已读概念；不按这个口径过滤，就会拿几天前
      它早回过几百遍的旧留言反复叫人。`〔代答〕` 是程序发的，不算本人发言。"""
    out = {}
    alias2slug = {}
    for name, meta in ((cfg or {}).get("agents") or {}).items():
        meta = meta or {}
        if meta.get("slug"):
            alias2slug[name] = meta["slug"]
    for row in read_ndjson(DIALOG_SRC):
        slug = alias2slug.get(str(row.get("from") or ""))
        if not slug:
            continue
        if str(row.get("body") or "").startswith("〔代答〕"):
            continue
        ms = ts_ms(row.get("ts"))
        if ms > out.get(slug, 0):
            out[slug] = ms
    return out


def effective_watermark_ms(state, slug, spoken):
    """门铃"未读水位" = max( 本人最后一次看板发言 , 本人最后一次**成功送达**的门铃 )。

    ★ 2026-09-13 老板定：「组员级的根本没必要出现在看板里面……看板只有老板、总监和组长可以发」。
      （老板随即勘误：组员**在看板里可见、只读**，不是不该出现；只是**不该在里面发言**。）
      后果：**板行水位对组员恒为 0** —— 只按板行判，组员会被同一封信反复叫到天亮（实测：适配线
      水位冻在 03:23、连敲三次；唤醒通道线 9/12 同一批 6 条连报 3 次）。
      修法：**叫过一次（投递成功）就抬水位**——同一封信只推一次；有新信才再推。
      （投递**失败**不抬水位 → 下次还会重试，保证"叫不醒"仍能被发现。）
    """
    board_ms = int(spoken.get(slug, 0) or 0)
    # ★ 水位要按**被推那封信自己的 ts**算，不能按"推送发生的时刻"——
    #   否则"推送那一刻之后、同一分钟内到达的新信"会被当成已读、白白吞掉一条（自测抓到）。
    own_ms = int((state.get("pushedWm") or {}).get(slug, 0) or 0)
    return max(board_ms, own_ms, int((HUB_PUSHED or {}).get(slug, 0) or 0))


# ── ★ 两条叫醒通道合一（老板 2026-09-13 04:5x："按可靠的方式改一下"）──────────────
#   现状：同一封信会被**叫两次**——① Hub 在投递时推"（看板信箱来信提示）…"（带正文，走同一个
#   平台原语 `codex queue`）② 小工 30 秒节拍的门铃（只报条数）。
#   可靠口径（不是"删掉一条"，而是"分工 + 兜底"）：
#     · **正常只叫一次**：谁先把这条信推出去，谁记账；另一条通道看到账就**不再叫**。
#     · **异常有兜底**：推送**失败**不记账 → 另一条通道照常叫（今晚两次"投递失败"都属这类）。
#     · **久不处理慢速再催**：首次触达后，本人既没上板、也没投过信 → 30 分钟、2 小时各再叫一次，
#       之后安静（不无限刷，也不让一封信永远躺着）。
#   记账文件 = `outputs/dialog/pushed.ndjson`（append-only，Hub 与小工**共用一份**；两边都写、都读）。
PUSHED_LEDGER = os.path.join(DIALOG, "pushed.ndjson")
POKE_LADDER_MS = [30 * 60 * 1000, 2 * 60 * 60 * 1000]
HUB_PUSHED = {}          # 每轮刷新：slug -> 该线最后一次"被 Hub 成功推送"的 ms
HUB_PUSHED_CNT = {}      # 每轮刷新：(slug, 分钟) -> 该分钟被推过几封（防"同分钟吞信"）
# 会话账本目录（判"它动过没有"用；可用环境变量指到别处，自测靠它做隔离）
SESSIONS_DIR = os.environ.get("MCHAT_SESSIONS_DIR") or os.path.join(os.path.expanduser("~"), ".codex", "sessions")
SESSION_TURN_CACHE = {}  # 每轮刷新：threadId -> 该会话账本最后写入 ms
SLUG_TID = {}            # 每轮刷新：slug -> threadId


def refresh_hub_pushed(state=None, alias2slug=None):
    """读共用记账 → `(每线被推那封信的 ms, 每「线+分钟」被推了几封)`。

    两条硬口径（看板编辑 05:20 提的两点，我核对后采纳）：
      · **跳过 `mailbox_ts` 为空的记录**：他对"没有信"的推送（派单提示/唤醒补投）写空串，
        那种行**不能拿去抬水位**——否则会把同一分钟的真信一起吞掉；
      · **分钟精度会撞车**：同一分钟里两封**不同**的信，只按"最大 ts"判会把第二封当成已读 →
        所以额外记"这一分钟被推过几封"，按**分钟 + 条数**判（第 3 条见 unread 侧）。
    """
    mx, cnt = {}, {}
    # ★ 键空间归一（2026-09-13 05:47 `codex-看板编辑` 抓到的根因，**是我的错**）：
    #   账本的 `to` 按我的需求定义是**看板名**（Hub 照定义写的），而**我自己的小工写的是 slug** →
    #   两边键对不上 → "另一条通道看到账就不再叫"永远匹配不上 → 同一封信被**两个通道各推一次**
    #   （铁证：`05:45:15 by=hub to=codex-看板编辑` / `05:45:16 by=crew_host to=codex-convtool`，同一封、差 1 秒）。
    #   修法：**写入统一看板名**；**读取一律归一到 slug**（历史行不用改写）。
    a2s = alias2slug or {}
    if os.path.exists(PUSHED_LEDGER):
        for row in read_ndjson(PUSHED_LEDGER):
            to_raw = str(row.get("to") or "")
            to = a2s.get(to_raw, to_raw)
            mts = str(row.get("mailbox_ts") or "").strip()
            if not to or not mts:
                continue
            ms = ts_ms(mts)
            if not ms:
                continue
            if ms > mx.get(to, 0):
                mx[to] = ms
            key = (to, mts[:16])
            cnt[key] = cnt.get(key, 0) + 1
    # ★ 读取侧防护（看板编辑 05:45 建议，我采纳）：账本**缺失 / 读到 0 行**时**沿用上次水位**，
    #   绝不当成"归零"。理由：这份账本有多个写方，一次"另写新文件 + 替换"的瞬间（或任何外部重排）
    #   都会让读方看到空文件——那时若按"归零"判，就是**全员被重叫一次**（我 05:41 那次多叫就是这么来的）。
    if not mx and state is not None:
        prev = state.get("hubPushedCache") or {}
        pmx = {k: int(v) for k, v in (prev.get("mx") or {}).items()}
        pcnt = {}
        for k, v in (prev.get("cnt") or {}).items():
            a, _sep, b = str(k).partition("|")
            if a and _sep:
                pcnt[(a, b)] = int(v)
        if pmx:
            return pmx, pcnt
    if state is not None and mx:
        state["hubPushedCache"] = {"mx": {k: int(v) for k, v in mx.items()},
                                   "cnt": {"%s|%s" % (k[0], k[1]): int(v) for k, v in cnt.items()}}
    return mx, cnt


def split_unread(rows, slug, spoken, state):
    """把信箱行分成"真未读 / 已推过"。

    口径 = 板行 ∪ 小工自己的水位 ∪ Hub 记账；**一律按"那一分钟被推过几封"精细判**：
    同一分钟里只要有一封没推过，它就仍然是未读（防"同分钟吞信"）。
    """
    board_ms = int(spoken.get(slug, 0) or 0)
    own_ms = int((state.get("pushedWm") or {}).get(slug, 0) or 0)
    hub_ms, hub_cnt = HUB_PUSHED, HUB_PUSHED_CNT
    hmax = max(own_ms, int(hub_ms.get(slug, 0) or 0))
    cnt = {}
    for (s, minute), n in hub_cnt.items():
        if s == slug:
            cnt[minute] = cnt.get(minute, 0) + int(n or 0)
    if own_ms:      # 本机水位（含老状态迁移出来的那条）也算"那一分钟推过 1 封"
        om = datetime.fromtimestamp(own_ms / 1000.0).strftime("%Y-%m-%d %H:%M")
        cnt[om] = max(cnt.get(om, 0), 1)
    seen_in_min = {}
    unread = []
    for r in rows:
        ts = str(r.get("ts") or "")
        t = ts_ms(ts)
        minute = ts[:16]
        idx = seen_in_min.get(minute, 0)
        seen_in_min[minute] = idx + 1
        if t <= board_ms or t < hmax:
            continue
        if t == hmax and idx < int(cnt.get(minute, 0) or 0):
            continue
        unread.append(r)
    return unread


def record_push(to_name, mailbox_ts, by="crew_host"):
    """把"这条信已经推给这条线"记进共用账本（append-only；失败静默，不影响叫醒）。

    ★ `to_name` 一律传**看板名**（与需求定义、与 Hub 侧一致）——传 slug 会让两边对不上账。
    """
    try:
        with open(PUSHED_LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "ts_ms": int(time.time() * 1000), "by": by,
                                "to": to_name, "mailbox_ts": mailbox_ts}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def outbound_last_ms(agents):
    """各线**最后一次投出信**的时刻（slug -> ms）。
    用途：慢速兜底前先看本人有没有动作——投过信也算动作（组员不上板，不能只认板行）。"""
    name2slug = {}
    for name, meta in (agents or {}).items():
        if (meta or {}).get("slug"):
            name2slug[name] = meta["slug"]
    out = {}
    try:
        for fn in os.listdir(DIALOG):
            if not (fn.startswith("pending_") and fn.endswith(".ndjson")):
                continue
            for row in read_ndjson(os.path.join(DIALOG, fn)):
                slug = name2slug.get(str(row.get("from") or ""))
                ms = ts_ms(row.get("ts"))
                if slug and ms > out.get(slug, 0):
                    out[slug] = ms
    except Exception:
        pass
    return out


def acted_since(slug, since_ms, spoken, outbound):
    """本人自那封信之后有没有**动作**。

    三种都算动作（2026-09-13 05:54 `codex-量化总监` 报的假阳性，我采纳）：
      ① 上过板；② 投出过信；③ **会话里起过回合**。
    ★ ③ 是必须的：新规矩"回执走信箱、组员不上板"之后，**只在对话框里回话**（最正常的处理方式）
      在旧判据里等于"装死" → 被慢速兜底追着叫。会话账本（rollout）的写入时刻就是"它动过"的证据。
    """
    since_ms = int(since_ms or 0)
    if int(spoken.get(slug, 0) or 0) > since_ms:
        return True
    if int(outbound.get(slug, 0) or 0) > since_ms:
        return True
    tid = (SLUG_TID or {}).get(slug)
    return bool(tid) and session_turn_ms(tid) > since_ms


def session_turn_ms(tid):
    """本线会话账本最后写入的时刻（≈ 它最近起过一次回合）。取不到返回 0。每轮缓存。"""
    if not tid:
        return 0
    if tid in SESSION_TURN_CACHE:
        return SESSION_TURN_CACHE[tid]
    ts = 0
    try:
        for p in glob.glob(os.path.join(SESSIONS_DIR, "**", "rollout-*%s*.jsonl" % tid), recursive=True):
            ts = max(ts, int(os.path.getmtime(p) * 1000))
    except Exception:
        ts = 0
    SESSION_TURN_CACHE[tid] = ts
    return ts


def poke_due(state, slug, now_ms, spoken, outbound):
    """慢速兜底：首次触达后本人一直没动作 → 30 分钟、2 小时各再叫一次，之后安静。
    返回还要等多少毫秒（`None` = 不用兜底 / 该安静了）。"""
    pk = (state.get("poked") or {}).get(slug)
    if not pk:
        return None
    times = int(pk.get("times", 0) or 0)
    if times < 1 or times > len(POKE_LADDER_MS):
        return None
    if acted_since(slug, ts_ms(pk.get("mailTs")), spoken, outbound):
        return None
    wait = POKE_LADDER_MS[min(times - 1, len(POKE_LADDER_MS) - 1)]
    left = wait - (int(now_ms) - int(pk.get("lastAt", 0) or 0))
    return left if left <= 0 else None


def mark_poked(state, slug, mailbox_ts, now_ms):
    """记一次触达（首触与兜底共用）：同一封信连续触达就 +1，换新信就归 1。"""
    pk = state.setdefault("poked", {})
    cur = pk.get(slug) or {}
    same = str(cur.get("mailTs") or "") == str(mailbox_ts or "")
    pk[slug] = {"mailTs": mailbox_ts, "times": (int(cur.get("times", 0) or 0) + 1) if same else 1,
                "lastAt": int(now_ms)}
    # ★ 水位：记"被推那封信的 ts"（不是推送时刻）——同一分钟内到达的新信不能被吞（自测抓到）
    state.setdefault("pushedWm", {})[slug] = ts_ms(mailbox_ts)


def msg_hash(msg):
    """铃内容短哈希（8 位）——日志里用来判"两条铃到底是不是同一条"。

    ★ 2026-09-13 05:46 `codex-看板编辑` 报的真缺陷：日志原来写 `msg[:60]`（P0 是 `[:70]`），
      铃正文约 190 字 → **恰好把末尾的【最新一条 <ts>】截掉**，而那是判"新信 / 补送 / 重复"的**唯一判据字段**。
      所以日志改成记**判据字段**：`ts=`（最新一条）/ `n=`（条数）/ `lvl=`（级别）/ `h=`（内容哈希）。
    """
    return hashlib.sha1(str(msg).encode("utf-8")).hexdigest()[:8]


BOARD_URL = "http://100.64.75.72:8788/api/post"
TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".codex", "mobile_chat", "token.txt")


def post_board(body, author="codex-总监"):
    """往看板写一行（实名）。只给"自动门禁"这类**有据可查**的动作回执用。"""
    import urllib.request

    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        tok = f.read().strip()
    data = json.dumps({"author": author, "target": "老板", "body": body}).encode("utf-8")
    req = urllib.request.Request(
        BOARD_URL, data=data,
        headers={"Content-Type": "application/json; charset=utf-8", "x-mchat-token": tok},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def windows_path(ws):
    """只处理 Windows 工位。

    agents.json 里有 WSL 工位（如 `/home/lgy/lab/股票`）——在 Windows 上
    os.path.join('/home/...') 会被当成"C 盘根下"，**会乱造目录**，
    所以这里明确跳过；WSL 侧的镜像由 WSL 侧脚本或 Hub 负责。
    """
    ws = str(ws or "")
    if re.match(r"^[A-Za-z]:[\\/]", ws):
        return ws
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", ws)          # /mnt/e/xxx -> E:\xxx
    if m:
        return "%s:\\%s" % (m.group(1).upper(), m.group(2).replace("/", "\\"))
    return None


def worker_mirror_mailbox(state, dry, args):
    """把各线信箱里比游标新的留言，抄一份到它的工位。幂等：游标只前进。"""
    cfg = load_json(AGENTS, {})
    agents = cfg.get("agents", {}) if isinstance(cfg, dict) else {}
    cursors = state.setdefault("mirror", {})
    moved = 0
    for name, meta in agents.items():
        meta = meta or {}
        slug = meta.get("slug")
        ws = meta.get("workspace")
        if not slug or not ws:
            continue
        win_ws = windows_path(ws)
        if not win_ws:
            log("mirror-mailbox: 跳过 %s（工位不是 Windows 路径：%s）" % (slug, ws), dry)
            continue
        box = os.path.join(DIALOG, "pending_%s.ndjson" % slug)
        if not os.path.exists(box):
            continue
        rows = read_ndjson(box)
        if not rows:
            continue
        cur = cursors.get(slug)
        if cur is None:                      # 第一次：只搬最近 3 条，避免洪水
            rows = rows[-3:]
        else:
            rows = [r for r in rows if ts_key(r.get("ts")) > ts_key(cur)]
        if not rows:
            continue
        target_dir = os.path.join(win_ws, ".private", slug)      # 工位内的私人文件夹
        if args.target_root:
            target_dir = os.path.join(args.target_root, slug)
        target = os.path.join(target_dir, "inbox.md")
        log("mirror-mailbox: %s -> %s (%d 条)" % (slug, target, len(rows)), dry)
        if not dry:
            os.makedirs(target_dir, exist_ok=True)
            new = not os.path.exists(target)
            with open(target, "a", encoding="utf-8") as f:
                if new:
                    f.write("# 收件箱（由 crew_host 镜像自 outputs/dialog/pending_%s.ndjson）\n\n" % slug)
                for r in rows:
                    f.write("## [投递 %s] 来自 %s\n%s\n\n" % (r.get("ts", "?"), r.get("from", "?"), r.get("body", r.get("_raw", ""))))
            cursors[slug] = rows[-1].get("ts")
            moved += len(rows)
    return moved


def worker_heartbeat(state, dry, args):
    line = "%s workers=%s mirror_total=%s pid=%s" % (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), args.only or "all",
        state.get("mirror_total", 0), os.getpid())
    log("heartbeat: " + line, dry)
    if not dry:
        try:
            with open(HEARTBEAT, "w", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
    return 0


# ————————————————————————————————————————————————
# doorbell-queue：门铃 —— 用 `codex queue` 往既有会话投一条消息，**不抢写锁**
# 实测依据：2026-09-11 21:42，老板用 `codex queue` 对「已打开、被持锁」的本线投递成功，
#           我的 rollout 立刻出现 task_started → 这就是"打开也能叫醒"的真门铃。
# 纪律：① 只投"指针"（不替本尊编内容）；② 每条线 10 分钟最多一次；
#       ③ 同批留言不重复投；④ **只调 codex.exe queue**，绝不启动/停止任何进程。
# ————————————————————————————————————————————————
DOORBELL_COOLDOWN = 600
MAX_RING_PER_RUN = 2      # 单轮最多敲 2 条线，避免"第一次跑把大家全叫起来"
MAX_ATTEMPTS = 3          # 同一批留言最多敲 3 次；到顶仍无动静就停手并告警（防炸）
MAX_PER_HOUR = 20         # 每线每小时最多唤 20 次（防炸）；**新消息不因冷却被吞**
RETRY_LADDER = [1800, 3600, 7200]   # 敲满 MAX_ATTEMPTS 后改长间隔续叫：30 分钟 → 1 小时 → 2 小时（永不放弃）

# ── ★ P0「老板优先」通道（老板 2026-09-13 定：「老板的公告和门铃永远优先处理」）──────────
#   判定：来信人是「老板」，或正文是【公告】/（公告 N-xxxx 投递提示）/（催办 · 公告 N-xxxx）。
#   待遇：① 排序**永远排最前**（不吃轮转顺序、不被普通信挤掉）
#         ② **不吃**道普通限流（单轮 2 条 / 每线每小时 20 次 / 600 秒冷却）→ 改用下面的 P0_*
#         ③ 提示语带【老板·优先｜先办这条】前缀，被叫的线一眼知道先办它
#   不变：仍按"比本人上次看板发言更新"才算未读 —— 处理完回一行就停，不会无限叫。
P0_ENABLED = True            # ★ 总开关：回滚 = 把这里改成 False（行为立刻退回"没有 P0 通道"）
P0_MAX_RING_PER_RUN = 6      # 单轮最多敲 6 条 P0（其余下一轮 30 秒内接着敲，不饿死）
P0_PER_HOUR = 60             # P0 每线每小时上限（防炸；仍远高于普通的 20）
P0_COOLDOWN = 120            # P0 同一批最短 120 秒后可再敲（普通是 600 秒）
P0_SENDERS = {"老板"}
# ★ 2026-09-13 07:40 收窄（`codex-唤醒通道` 报、`codex-看板编辑` 核实转来）：
#   **P0 只认「发件人=老板」＋「真公告（正文以【公告 开头）」**。
#   原来把 `（催办 · 公告 …）` 和 `（公告 … 投递提示）` 也算 P0 —— 那是**机器人催办借用老板的优先级与文案**：
#   它会带着【老板·优先｜先办这条】下来，抢占所有线的队列与额度，看起来像老板在说话。**错误已修。**
P0_BODY_RE = re.compile(r"^\s*【公告")


def is_priority_row(row):
    """这条信箱记录是不是「老板优先」(P0)。**纯函数**（便于自测；不碰文件、不碰状态）。"""
    row = row or {}
    if str(row.get("from") or "") in P0_SENDERS:
        return True
    return bool(P0_BODY_RE.match(str(row.get("body") or "")))


def find_git_dir():
    """找 git 所在目录（计划任务的 PATH 里通常没有 git——Codex 自带的那份更不在）。
    返回目录或 None；只做查找，不执行任何命令。"""
    import shutil

    w = shutil.which("git")
    if w:
        return os.path.dirname(w)
    cands = [
        r"C:\Program Files\Git\cmd",
        r"C:\Program Files (x86)\Git\cmd",
        os.path.join(os.path.expanduser("~"), ".cache", "codex-runtimes", "codex-primary-runtime",
                     "dependencies", "native", "git", "cmd"),
    ]
    for d in cands:
        if os.path.exists(os.path.join(d, "git.exe")):
            return d
    return None


def find_codex_exe():
    """找最新的 codex.exe——更新后哈希目录会变，所以每次现找。"""
    pat = os.path.join(os.environ.get("LOCALAPPDATA", ""), "OpenAI", "Codex", "bin", "*", "codex.exe")
    cands = glob.glob(pat)
    return max(cands, key=os.path.getmtime) if cands else None


def run_codex_queue(exe, thread_id, message):
    env = dict(os.environ)
    home = os.path.expanduser("~")
    env.setdefault("CODEX_HOME", os.path.join(home, ".codex"))
    env.setdefault("USERPROFILE", home)
    env.setdefault("HOME", home)
    r = subprocess.run([exe, "queue", "--thread", thread_id, "--message", message],
                       capture_output=True, text=True, timeout=90, env=env)
    return r.returncode, (r.stderr or r.stdout or "").strip()[:200]


def lock_present(thread_id):
    """该线程的写锁是否被持有（被持有=客户端占着=queue 通道；没持有=未加载=resume 通道）。"""
    p = os.path.join(os.path.expanduser("~"), ".codex", "thread-writer-locks", thread_id + ".lock")
    if not os.path.exists(p):
        return False
    try:
        with open(p, "r+b"):
            return False
    except Exception:
        return True


def run_codex_resume_bg(exe, thread_id, message):
    """未被占用 → 用 `codex exec resume` 起回合。**后台发起、不等待**（否则会阻塞 30 秒节拍）。"""
    env = dict(os.environ)
    home = os.path.expanduser("~")
    env.setdefault("CODEX_HOME", os.path.join(home, ".codex"))
    env.setdefault("USERPROFILE", home)
    env.setdefault("HOME", home)
    flags = 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW
    p = subprocess.Popen([exe, "exec", "resume", "--skip-git-repo-check", thread_id, "-"],
                         stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         text=True, env=env, creationflags=flags)
    try:
        p.stdin.write(message)
        p.stdin.close()
    except Exception:
        pass
    return 0, "resume(后台发起)"


def run_codex_wake(exe, thread_id, message):
    """**队列优先，但必须验证"真起了回合"；没起就落 resume。**

    · `codex queue` 对**应用里挂着的线**（含未加载的窗）有效；
    · **对"无窗实例"（`codex exec` 起的会话）queue 会被受理、但没人消费** ——
      2026-09-13 08:2x 重生实验实测：新实例账本 mtime 不动、板上无回话，
      改投 `codex exec resume` **立刻起回合**（它自己读包、按规矩回板）。
    · 所以判据不是"投递返回 0"，而是**它自己的账本有没有前进**（教训：投递OK ≠ 叫醒）。
    """
    before = rollout_mtime_ms(thread_id)
    code, err = run_codex_queue(exe, thread_id, message)
    if code == 0 and turn_started(thread_id, before, 8):
        return code, err, "queue"
    code2, err2 = run_codex_resume_bg(exe, thread_id, message)
    return code2, err2, "resume(备选)" + ("" if code == 0 else "(queue 失败)") + (
        "(queue 受理但没起回合)" if code == 0 else "")


def rollout_path(tid):
    """按 threadId 找它自己的会话账本（找不到返回 None）。"""
    try:
        hits = glob.glob(os.path.join(SESSIONS_DIR, "**", "rollout-*%s*.jsonl" % tid), recursive=True)
        return max(hits, key=os.path.getmtime) if hits else None
    except Exception:
        return None


def rollout_mtime_ms(tid):
    p = rollout_path(tid)
    try:
        return int(os.path.getmtime(p) * 1000) if p else 0
    except Exception:
        return 0


def turn_started(tid, before_ms, secs):
    """在 `secs` 秒内，该线账本有没有前进（= 真起了回合）。"""
    for _ in range(max(1, int(secs))):
        if rollout_mtime_ms(tid) > int(before_ms or 0):
            return True
        time.sleep(1)
    return False


def ring_priority(state, dry, exe, cfg, spoken, now):
    """★ P0 通道：**老板的公告/门铃永远先敲**，且不吃普通限流（2026-09-13 老板定）。

    与普通轮的区别：
      · 只认"老板发来的"或"公告类"的未读（`is_priority_row`）；
      · 排序上先于一切普通线（本函数在普通轮之前整体跑一遍）；
      · 冷却 120 秒（普通 600 秒）、每小时上限 60（普通 20）、单轮上限 6（普通 2）；
      · 提示语带【老板·优先｜先办这条】，被叫的线一眼知道先办它。
    仍沿用同一条水位口径（比本人上次看板发言更新才算未读）→ 处理完回一行就停，不会无限叫。
    """
    if not P0_ENABLED:                      # ← 回滚开关：关掉即恢复旧行为
        return 0
    agents = cfg.get("agents", {}) if isinstance(cfg, dict) else {}
    last_at = state.setdefault("queuedAt", {})
    fired = 0
    for name, meta in agents.items():
        meta = meta or {}
        slug, tid = meta.get("slug"), meta.get("threadId")
        if not slug or not tid or meta.get("status") == "retired":
            continue
        box = os.path.join(DIALOG, "pending_%s.ndjson" % slug)
        if not os.path.exists(box):
            continue
        rows = read_ndjson(box)
        unread = split_unread(rows, slug, spoken, state)
        if not any(is_priority_row(r) for r in unread):
            continue
        newest = unread[-1].get("ts")
        att = state.setdefault("attempts", {}).get(slug, [None, 0])
        if att[0] == newest and now - float(last_at.get(slug, 0)) < P0_COOLDOWN:
            continue
        hits = [t for t in state.setdefault("hourHits", {}).get(slug, []) if now - t < 3600]
        if len(hits) >= P0_PER_HOUR:
            log("doorbell-queue[P0]: %s 本小时已达 P0 上限 %d，跳过" % (slug, P0_PER_HOUR), dry)
            continue
        if fired >= P0_MAX_RING_PER_RUN:
            log("doorbell-queue[P0]: 本轮已达 P0 上限 %d，剩余下一轮（30 秒内）再敲" % P0_MAX_RING_PER_RUN, dry)
            break
        senders = sorted({str(r.get("from", "?")) for r in unread[-3:]})
        lvl = str((agents.get(name) or {}).get("level") or "").lower()
        msg = ("【老板·优先｜先办这条】【信箱%s】你有 %d 条待读留言（来自 %s）。"
               "请看工位 .private\\%s\\inbox.md，处理后回看板一行即可（≤200 字）。"
               "【最新一条 %s】—— crew_host P0 doorbell"
               % ("·" + lvl if lvl else "", len(unread), "、".join(senders), slug, newest))
        log("doorbell-queue → %s (%s)[P0]：ts=%s n=%d lvl=%s h=%s"
            % (slug, str(tid)[:8], newest, len(unread), lvl or "-", msg_hash(msg)), dry)
        if dry:
            continue
        try:
            code, err, chan = run_codex_wake(exe, tid, msg)
            if code == 0:
                fired += 1
                state.setdefault("queued", {})[slug] = newest
                last_at[slug] = now
                state.setdefault("attempts", {})[slug] = [newest, (att[1] if att[0] == newest else 0) + 1]
                hh = state.setdefault("hourHits", {}).setdefault(slug, [])
                hh.append(now)
                state["hourHits"][slug] = hh[-50:]
                mark_poked(state, slug, newest, now * 1000)   # ★ 触达记账（兜底阶梯用）
                for _r in unread:                             # ★ 一封一行：同分钟多封才不会被吞
                    record_push(name, _r.get("ts"))          # ★ 写**看板名**（键空间统一）
                log("doorbell-queue: %s 投递OK via %s（P0 第 %d 次）"
                    % (slug, chan, state["attempts"][slug][1]), dry)
            else:
                log("doorbell-queue: %s P0 失败(code=%s, %s) %s" % (slug, code, chan, err), dry)
        except Exception as e:
            log("doorbell-queue: %s P0 异常 %r" % (slug, e), dry)
    return fired


def worker_doorbell_queue(state, dry, args):
    """拿到新留言的线 → 用 codex queue 敲它一下（只投指针，不替它编内容）。

    ★ 两步走：先 `ring_priority()` 敲**老板的公告/门铃**（P0，永远排最前），再走普通轮转。
    """
    exe = find_codex_exe()
    if not exe:
        log("doorbell-queue: 找不到 codex.exe，跳过", dry)
        return 0
    cfg = load_json(AGENTS, {})
    agents = cfg.get("agents", {}) if isinstance(cfg, dict) else {}
    # ★ 只叫"真未读"（2026-09-12 二次落地）：信箱是 append-only 流水、没有已读概念，
    #   老逻辑会把**它早回过几百遍的旧留言**当成待读，反复叫人去清同一批
    #   （实测：codex-总监 被同一批"9/10 条"连叫数轮）。口径 = 比它**上次本人在看板发言**更新的才算未读。
    spoken = read_last_spoken(cfg)
    queued = state.setdefault("queued", {})
    last_at = state.setdefault("queuedAt", {})
    now = time.time()
    fired = 0
    # ★ 两条通道合一：先把"Hub 已经推过谁"的账本读进来（没有这个文件就按老行为跑）
    global HUB_PUSHED
    global HUB_PUSHED_CNT
    _a2s = {}
    for _n, _m in agents.items():
        if (_m or {}).get("slug"):
            _a2s[_n] = _m["slug"]
    global SLUG_TID, SESSION_TURN_CACHE
    SLUG_TID = {(_m or {}).get("slug"): (_m or {}).get("threadId") for _m in agents.values() if (_m or {}).get("slug")}
    SESSION_TURN_CACHE = {}          # 每轮重算"它最近动过没有"
    HUB_PUSHED, HUB_PUSHED_CNT = refresh_hub_pushed(state, _a2s)   # ★ 读取归一到 slug
    # ★ 老状态迁移（2026-09-13 05:1x）：换水位来源前，"最后成功推送的那封信"记在
    #   `attempts[slug][0]`（就是那封信的 ts）。不补这一步，刚上线时**每条线会各多叫一次**
    #   （实测现场：hr / render / adapter / config 各被多叫一次——适配线、配置线当场报了案）。
    _wm = state.setdefault("pushedWm", {})
    for _slug, _att in (state.get("attempts") or {}).items():
        _ts = _att[0] if isinstance(_att, list) and _att else None
        if _ts and not _wm.get(_slug):
            _wm[_slug] = ts_ms(_ts)
    # ★ P0：老板的公告/门铃**先敲**，独立限流、独立提示语；普通轮转随后。
    ring_priority(state, dry, exe, cfg, spoken, now)
    outbound = None          # 慢速兜底时才去算（省得每轮扫 15 个信箱）
    # **轮转起点**（2026-09-12 修）：原来每轮都从 agents.json 第一条开始，而
    # `MAX_RING_PER_RUN` 一到就 break —— 排在后面的线（如 codex-套件）会被**永远饿死**，
    # 明明信箱里有未读、却一次也响不到。改成每轮起点往后挪一位。
    order = list(agents.items())
    if order:
        rr = int(state.get("rr", 0)) % len(order)
        state["rr"] = (rr + 1) % len(order)
        order = order[rr:] + order[:rr]
    for name, meta in order:
        meta = meta or {}
        slug, tid = meta.get("slug"), meta.get("threadId")
        if not slug or not tid or meta.get("status") == "retired":
            continue
        box = os.path.join(DIALOG, "pending_%s.ndjson" % slug)
        if not os.path.exists(box):
            continue
        rows = read_ndjson(box)
        if not rows:
            continue
        unread = split_unread(rows, slug, spoken, state)
        if not unread:
            # ★ 慢速兜底：已经叫过、本人却一直没动作 → 30 分钟 / 2 小时各再叫一次
            if outbound is None:
                outbound = outbound_last_ms(agents)
            if poke_due(state, slug, now * 1000, spoken, outbound) is not None:
                att = state.setdefault("attempts", {}).get(slug, [None, 0])
                newest_pk = ((state.get("poked") or {}).get(slug) or {}).get("mailTs")
                hits = [t for t in state.setdefault("hourHits", {}).get(slug, []) if now - t < 3600]
                if len(hits) >= MAX_PER_HOUR:
                    continue
                if fired >= MAX_RING_PER_RUN:
                    break
                msg = ("【还没动静】这条信我 %s 前就推给你了，你既没回信、没上板、会话也没动静。"
                       "请看工位 .private\\%s\\inbox.md 后回一句；**若你其实已经处理过，忽略这条即可**——"
                       " crew_host doorbell" % (int(POKE_LADDER_MS[min(int((state.get('poked') or {}).get(slug, {}).get('times', 1)) - 1, len(POKE_LADDER_MS) - 1)] / 60000), slug))
                log("doorbell-queue[兜底] → %s (%s)：ts=%s n=1 lvl=%s h=%s"
                    % (slug, str(tid)[:8], newest_pk, str(meta.get("level") or "").lower() or "-", msg_hash(msg)), dry)
                if not dry:
                    try:
                        code, err, chan = run_codex_wake(exe, tid, msg)
                        if code == 0:
                            fired += 1
                            last_at[slug] = now
                            state.setdefault("attempts", {})[slug] = [newest_pk, int(att[1]) + 1]
                            hh = state.setdefault("hourHits", {}).setdefault(slug, [])
                            hh.append(now)
                            state["hourHits"][slug] = hh[-50:]
                            mark_poked(state, slug, newest_pk, now * 1000)
                            record_push(name, newest_pk)     # ★ 写**看板名**
                            log("doorbell-queue: %s 兜底投递OK via %s" % (slug, chan), dry)
                        else:
                            log("doorbell-queue: %s 兜底失败(code=%s, %s)" % (slug, code, err), dry)
                    except Exception as e:
                        log("doorbell-queue: %s 兜底异常 %r" % (slug, e), dry)
            continue
        # ★ 这条线有 P0 未读 → 已由 ring_priority 敲过，普通轮不再重复敲（防一封信两路各敲一次）。
        if P0_ENABLED and any(is_priority_row(r) for r in unread):
            continue
        newest = unread[-1].get("ts")
        att = state.setdefault("attempts", {}).get(slug, [None, 0])
        same_batch = (att[0] == newest)                # 同一批（重试）还是新消息
        # 限速：同一批前 MAX_ATTEMPTS 次按 10 分钟一次；**之后不再永久停手**，改长间隔续叫。
        # （2026-09-12 老板问"为什么叫不醒"：旧逻辑到顶就永久静默，等于"叫三遍没人应就再也不叫"。
        #   但"投递成功" ≠ "对方真的开工了"，所以必须一直保持能叫醒。）
        if same_batch:
            n = att[1]
            wait = DOORBELL_COOLDOWN if n < MAX_ATTEMPTS else RETRY_LADDER[min(n - MAX_ATTEMPTS, len(RETRY_LADDER) - 1)]
            if now - float(last_at.get(slug, 0)) < wait:
                continue
        hits = [t for t in state.setdefault("hourHits", {}).get(slug, []) if now - t < 3600]
        if len(hits) >= MAX_PER_HOUR:
            log("doorbell-queue: %s 本小时已达上限 %d，跳过" % (slug, MAX_PER_HOUR), dry)
            continue
        senders = sorted({str(r.get("from", "?")) for r in unread[-3:]})
        lvl = str(meta.get("level") or "").lower()
        msg = ("【信箱%s】你有 %d 条待读留言（来自 %s）。请看工位 .private\\%s\\inbox.md，"
               "处理后回看板一行即可（≤200 字）。【最新一条 %s】——crew_host doorbell"
               % ("·" + lvl if lvl else "", len(unread), "、".join(senders), slug, newest))
        log("doorbell-queue → %s (%s)：ts=%s n=%d lvl=%s h=%s"
            % (slug, str(tid)[:8], newest, len(unread), lvl or "-", msg_hash(msg)), dry)
        if dry:
            continue
        try:
            code, err, chan = run_codex_wake(exe, tid, msg)
            if code == 0:
                fired += 1
                queued[slug] = newest
                last_at[slug] = now
                state.setdefault("attempts", {})[slug] = [newest, (att[1] if att[0] == newest else 0) + 1]
                hh = state.setdefault("hourHits", {}).setdefault(slug, [])
                hh.append(now)
                state["hourHits"][slug] = hh[-50:]
                mark_poked(state, slug, newest, now * 1000)   # ★ 触达记账（兜底阶梯用）
                for _r in unread:                             # ★ 一封一行：同分钟多封才不会被吞
                    record_push(name, _r.get("ts"))          # ★ 写**看板名**
                log("doorbell-queue: %s 投递OK via %s（第 %d 次）"
                    % (slug, chan, state["attempts"][slug][1]), dry)
            else:
                log("doorbell-queue: %s 失败(code=%s, %s) %s" % (slug, code, chan, err), dry)
        except Exception as e:
            log("doorbell-queue: %s 异常 %r" % (slug, e), dry)
        if fired >= MAX_RING_PER_RUN:
            log("doorbell-queue: 本轮已达上限 %d，其余下次再叫" % MAX_RING_PER_RUN, dry)
            break
    return fired


def worker_auto_merge(state, dry, args):
    """**审阅→合入的自动化**（老板 2026-09-12："这一步就不能自动化吗"）。

    只认 `outputs/merge/merge_request.json`：那是 `crew_review_merge.mjs --check` 的产出，
    门禁（测试全绿 / 没碰契约 / 没删文件 / 署名合规 / 变更面非空）**全绿才会 ok=true**。
    小工只做一件事：照单合入 + 推 origin，然后把申请归档并在看板留一行。
    **申请没过门禁 → 一个字都不动**。"""
    req = os.path.join(OUT, "merge", "merge_request.json")
    if not os.path.exists(req):
        return 0
    r = load_json(req, {})
    if not r.get("ok"):
        log("auto-merge: 申请未过门禁 → 不合（等人来看）", dry)
        return 0
    repo, branch, task = r.get("repo"), r.get("branch"), r.get("task")
    log("auto-merge → %s %s（%s）" % (repo, branch, task), dry)
    if dry:
        return 0
    script = os.path.join(ROOT, "scripts", "crew_review_merge.mjs")
    try:
        # 计划任务的 PATH 很干净：git / node 往往**不在里面**（git 是 Codex 自带的那个）。
        # 所以这里显式补 PATH，否则 merge 会静默退出码 1（2026-09-12 实测踩过）。
        env = dict(os.environ)
        extra = [d for d in (find_git_dir(), r"C:\Program Files\nodejs", os.path.dirname(find_codex_exe() or "")) if d]
        env["PATH"] = ";".join(extra + [env.get("PATH", "")])
        p = subprocess.run(["node", script, "--apply"], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300, env=env)
        out = (p.stdout or "").strip().splitlines()
        err = (p.stderr or "").strip().splitlines()
        tail = out[-1] if out else (err[-1] if err else "(无输出)")
        log("auto-merge: 退出码 %s | %s" % (p.returncode, tail[:200]))
        if p.returncode != 0 and err:
            log("auto-merge: stderr | %s" % " / ".join(err[-3:])[:240])
        if p.returncode == 0:
            try:
                post_board(("〔自动门禁·codex-总监 授权〕**已自动合入** `%s` → `main`（%s）。"
                            "门禁全绿（测试/契约/删除/署名/变更面），未过门禁则不合。")
                           % (branch, task))
            except Exception as e:
                log("auto-merge: 回板失败 %r" % (e,))
    except Exception as e:
        log("auto-merge: 异常 %r" % (e,))
    return 1



WORKERS = {"mirror-mailbox": worker_mirror_mailbox, "heartbeat": worker_heartbeat,
           "doorbell-queue": worker_doorbell_queue, "auto-merge": worker_auto_merge}


def self_guard():
    """自检：本宿主**不调用任何进程控制**。

    交易链（引擎/托盘/stockdb/数据同步）只能由计划任务或老板本人拉起——
    所以这里写死一条机器可验的规矩：源码里不许出现进程控制调用。
    （关键词用拼串写，避免自检扫到自己。）
    """
    src = open(os.path.abspath(__file__), "r", encoding="utf-8").read()
    bad = ("task" + "kill", "Stop-" + "Process", "Start-" + "Process",
           "schtasks /" + "run", "os." + "system")
    return [b for b in bad if b in src]


def run_once(args):
    hits = self_guard()
    if hits:
        log("REFUSE: 源码里出现进程控制调用 %s —— 本宿主只做搬运，不碰任何进程" % (hits,))
        return 3
    state = load_json(STATE, {})
    names = [args.only] if args.only else list(WORKERS.keys())
    total = 0
    for n in names:
        fn = WORKERS.get(n)
        if not fn:
            log("未知小工: %s（可用：%s）" % (n, ", ".join(WORKERS)))
            continue
        try:
            total += fn(state, args.dry_run, args) or 0
        except Exception as e:
            log("小工 %s 出错: %r" % (n, e))
    state["mirror_total"] = state.get("mirror_total", 0) + total
    state["lastRun"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_json(STATE, state, args.dry_run)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="跑一遍就退出")
    ap.add_argument("--interval", type=int, default=0, help="常驻：每 N 秒跑一遍")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写任何东西")
    ap.add_argument("--only", default="", help="只跑某个小工")
    ap.add_argument("--target-root", default="", help="[测试用] 覆盖镜像目标根目录")
    args = ap.parse_args()

    if args.interval > 0 and not args.once:
        log("crew_host 启动：interval=%ss dry=%s only=%s" % (args.interval, args.dry_run, args.only or "all"))
        while True:
            maybe_self_reload()
            run_once(args)
            time.sleep(args.interval)
    return run_once(args)


SCRIPT_MTIME = os.path.getmtime(os.path.abspath(__file__))


def maybe_self_reload():
    """脚本被改过 → **自我重载**（老板不必每次手工 Stop/Start 计划任务）。

    2026-09-12 实测痛点：每次改这个文件都要老板重启计划任务，忘一次就跑着旧代码
    （"门铃写投递OK、其实没叫醒"就是这么来的）。"""
    try:
        cur = os.path.getmtime(os.path.abspath(__file__))
        if cur > SCRIPT_MTIME + 0.5:
            # 两道闸（2026-09-13 实测教训：宿主 00:09 后彻底没了心跳——
            # 很可能是改脚本的瞬间它自我重载，读到了**正在写入的半截文件** → 起不来）
            if time.time() - cur < 2:                     # 闸一：文件必须已静止 ≥2 秒
                log("crew_host: 脚本刚被改（<2s），等下一轮再重载")
                return
            try:                                          # 闸二：先确认能编译再换进程
                import py_compile
                py_compile.compile(os.path.abspath(__file__), doraise=True)
            except Exception as e:
                log("crew_host: 脚本更新但**编译不过**（可能在写入中）→ 本轮跳过重载：%r" % (e,))
                return
            log("crew_host: 检测到脚本更新（mtime 变了）→ 自我重载")
            os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])
    except Exception as e:
        log("crew_host: 自我重载失败（不影响本轮）：%r" % (e,))


if __name__ == "__main__":
    sys.exit(main())
