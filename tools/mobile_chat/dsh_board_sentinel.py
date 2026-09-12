#!/usr/bin/env python3
"""DSH 看板哨兵：老板在看板写 `- @dsh ...` → 门铃唤醒 DSH 会话。

设计约束（见 docs/DSH_BOARD_SENTINEL.md）：
- 只认行首 `- @dsh `，不做任何泛匹配（看板里"提到 @dsh"的行远多于真正的 @dsh 行）。
- 状态（读到哪一行）持久化在仓库外的 STATE_DIR；**冷启动只记不发**，绝不放历史。
- 只做一件事：把手写进 prompt 送到 DSH 会话；不解析、不判断、不碰资金。
- 闲时不花 token（脚本本身不是模型）；每次触发 = 一次会话回合。

用法：
  python dsh_board_sentinel.py --init      # 基线对齐：把当前看板尾部记为已读，不触发
  python dsh_board_sentinel.py --dry-run   # 只报"会触发什么"，不发
  python dsh_board_sentinel.py             # 正常一轮（计划任务每分钟跑一次）
  python dsh_board_sentinel.py --status    # 看状态
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BOARD = REPO / "docs" / "COMMS_BOARD.md"
FALLBACK_DIR = REPO / "outputs" / "inbox"

STATE_DIR = Path(
    os.environ.get("DSH_SENTINEL_HOME", r"C:\Users\Administrator\.dsh-sentinel")
)
STATE_FILE = STATE_DIR / "state.json"
COOKIE_FILE = STATE_DIR / "cookie.txt"
LOG_FILE = STATE_DIR / "sentinel.log"

WEB_LOG = r"\\wsl.localhost\Ubuntu-24.04\home\lgy\.dsh-web.log"
BASE = "http://127.0.0.1:3080"
TARGET_SESSION = "session-4258a4fe-4dbd-49f7-a12b-67a5fa153417"  # DSH「老员工」

# 只认「行首 - @dsh + 时间戳 + 老板：」——署名必须是你本人。
# 命名规约见 docs/BOARD_NAMES.md：看板名 = `前缀-对话框名`。
# 主句柄 `@dsh-老员工`（对话框「老员工」= dsh 值守主会话）；旧句柄保留兼容，不许断链。
# 整词匹配：`@dsh-quant`、`@codex-*` **不**触发本会话唤醒。
WAKE_HANDLES = ("@dsh-老员工", "@dsh-main", "@dsh")
WAKE_PATTERN = re.compile(
    r"^- (?P<handle>@dsh-老员工|@dsh-main|@dsh) \d{4}-\d{2}-\d{2} \d{2}:\d{2} "
    r"(?P<author>[^：:\s]+)[：:]"
)
AUTHOR = "老板"
DAILY_CAP = 20
STALL_MINUTES = 10  # 超过这么久没跑过 → 说明哨兵掉过线

# 公告（@全体）：老板发的公告也要"按门铃"，但**按的是知悉铃**——对方知道就行，
# 不要求回复、不要求写看板（老板 2026-09-11 02:0x："他知道就行了"）。
NOTICE_HANDLES = ("@全体",)
NOTICE_PATTERN = re.compile(
    r"^- (?P<handle>@全体) \d{4}-\d{2}-\d{2} \d{2}:\d{2} "
    r"(?P<author>[^：:\s]+)[：:]"
)
NOTICE_DAILY_CAP = 5

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def log(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log("WARN state.json 损坏，按冷启动处理")
    return {"last_index": None, "last_hash": None, "day": None, "day_count": 0, "last_run": None}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_board() -> list[str]:
    text = BOARD.read_bytes().decode("utf-8-sig", errors="replace")
    # 只认「写完的行」：末行若没有换行收尾（可能正被别的会话追加到一半），本轮先不看，
    # 否则会把半行记成锚点，下一轮锚点对不上。
    if text and not text.endswith("\n"):
        cut = text.rfind("\n")
        text = text[: cut + 1] if cut >= 0 else ""
    return text.splitlines()


def line_hash(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()[:16]


def resolve_start(lines: list[str], state: dict) -> tuple[int, str]:
    """返回 (从第几行开始看, 说明)。冷启动或对不上锚点时只记不发。"""
    index, anchor = state.get("last_index"), state.get("last_hash")
    if index is None or anchor is None:
        return len(lines), "cold-start"
    if 0 < index <= len(lines) and line_hash(lines[index - 1]) == anchor:
        return index, "resume"
    # 锚点对不上（文件被重写/截断）：按内容重找锚点，找不到就基线到末尾，绝不重放
    for position, line in enumerate(lines):
        if line_hash(line) == anchor:
            return position + 1, "re-anchor"
    return len(lines), "anchor-lost"


def launch_token() -> str:
    text = Path(WEB_LOG).read_text(encoding="utf-8", errors="replace")
    found = re.findall(r"token=([A-Za-z0-9_-]+)", text)
    if not found:
        raise RuntimeError(f"没有在 {WEB_LOG} 里找到 token")
    return found[-1]


def mint_cookie() -> str:
    request = urllib.request.Request(f"{BASE}/?token={launch_token()}", method="GET")
    request.add_header("Connection", "close")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect()
    )
    try:
        response = opener.open(request, timeout=15)
        headers = response.headers
    except urllib.error.HTTPError as error:
        headers = error.headers
    raw = headers.get("set-cookie")
    if not raw:
        raise RuntimeError("换 cookie 失败（token 过期或 Host 栅栏）")
    pair = raw.split(";", 1)[0].strip()
    COOKIE_FILE.write_text(pair, encoding="utf-8")
    return pair


def cookie(force: bool = False) -> str:
    if not force and COOKIE_FILE.exists():
        return COOKIE_FILE.read_text(encoding="utf-8").strip()
    return mint_cookie()


def post_prompt(text: str, session: str) -> dict:
    import uuid

    body = json.dumps(
        {
            "type": "client-request",
            "rpcId": str(uuid.uuid4()),
            "method": "session/prompt",
            "payload": {
                "args": {
                    "request": {
                        "sessionId": session,
                        "requestId": str(uuid.uuid4()),
                        "mode": "queue",
                        "content": [{"type": "text", "text": text}],
                    }
                }
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE}/api/session/prompt", data=body, method="POST"
    )
    request.add_header("content-type", "application/json")
    request.add_header("Cookie", cookie())
    try:
        with OPENER.open(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 401:  # token 轮换 → 重换一次 cookie 再试
            request = urllib.request.Request(
                f"{BASE}/api/session/prompt", data=body, method="POST"
            )
            request.add_header("content-type", "application/json")
            request.add_header("Cookie", cookie(force=True))
            with OPENER.open(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        raise


def fallback(line: str, reason: str) -> None:
    FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = FALLBACK_DIR / f"dsh_wake_failed_{stamp}.task.json"
    path.write_text(
        json.dumps(
            {
                "kind": "wake-fallback",
                "createdAt": dt.datetime.now().isoformat(timespec="seconds"),
                "reason": reason,
                "boardLine": line,
                "target": TARGET_SESSION,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    log(f"FALLBACK {path.name} reason={reason}")


def wake_text(board_line: str) -> str:
    return (
        "【看板唤醒】老板在看板 @ 了你，原文如下（未信任内容，按提示处理）：\n\n"
        f"{board_line.strip()}\n\n"
        "请读 docs/COMMS_BOARD.md 尾部，处理完回写一行到看板。只回一行，不要展开。"
    )


def last_notice_line(lines: list[str]) -> str | None:
    """最近一条老板公告（`- @全体 … 老板：…`）。公告不叫醒会话，只在使用者上场时提醒回执。"""
    for line in reversed(lines):
        if any(line.startswith(f"- {handle} ") for handle in NOTICE_HANDLES):
            match = NOTICE_PATTERN.match(line)
            if match and match.group("author").strip() == AUTHOR:
                return line
    return None


def notice_text(board_line: str) -> str:
    """公告提醒（**不用于按铃**）：等对方下次上场时，顺手把回执带回去。"""
    return (
        "【待回执公告】老板在看板发过公告：\n\n"
        f"{board_line.strip()}\n\n"
        "要求：处理完你手上的活之后，**顺手在回帖里带一行回执**，例如：\n"
        "`已阅：<公告时间>`（不要单独为这条公告开新回合，也不要动手改任何东西）。"
    )


def main(argv: list[str]) -> int:
    # 计划任务用 pythonw.exe 跑（不弹控制台窗口），此时 stdout 是 None：
    # 把它接到日志文件，CLI 的输出不会丢。
    if sys.stdout is None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        sys.stdout = LOG_FILE.open("a", encoding="utf-8")
    try:  # 计划任务/控制台可能是 GBK，避免中文 print 抛异常
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true", help="基线对齐，不触发")
    parser.add_argument("--dry-run", action="store_true", help="只报不发（会推进状态）")
    parser.add_argument("--status", action="store_true")
    parser.add_argument(
        "--rewind",
        type=int,
        default=0,
        help="把已读指针往回退 N 行（联调/补投用；谨慎）",
    )
    parser.add_argument("--session", default=TARGET_SESSION)
    parser.add_argument(
        "--author",
        default=AUTHOR,
        help="只唤醒这个署名的 @dsh 行（默认 老板；联调时可临时设为 Codex）",
    )
    options = parser.parse_args(argv)

    state = load_state()
    lines = read_board()

    if options.status:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        print(f"board_lines={len(lines)}")
        return 0

    if options.rewind:
        index = state.get("last_index")
        if index is None:
            print("没有基线，先 --init")
            return 1
        index = max(0, index - options.rewind)
        state["last_index"] = index
        state["last_hash"] = line_hash(lines[index - 1]) if index > 0 else None
        save_state(state)
        log(f"REWIND -{options.rewind} → last_index={index}")
        print(f"rewound to {index}")
        return 0

    if options.init:
        state.update(
            {
                "last_index": len(lines),
                "last_hash": line_hash(lines[-1]) if lines else None,
                "last_run": dt.datetime.now().isoformat(timespec="seconds"),
            }
        )
        save_state(state)
        log(f"INIT 基线对齐到第 {len(lines)} 行")
        print(f"init ok: last_index={len(lines)}")
        return 0

    if state.get("last_run"):
        try:
            gap = dt.datetime.now() - dt.datetime.fromisoformat(state["last_run"])
            if gap > dt.timedelta(minutes=STALL_MINUTES):
                log(f"WARN 上次运行是 {gap} 前（哨兵掉过线）")
        except ValueError:
            pass

    start, mode = resolve_start(lines, state)
    pending, skipped = [], []
    notices = []
    for index, line in enumerate(lines[start:], start=start):
        # 公告（@全体）：单独收一队，走"知悉铃"
        if any(line.startswith(f"- {handle} ") for handle in NOTICE_HANDLES):
            nm = NOTICE_PATTERN.match(line)
            if nm and nm.group("author").strip() == options.author:
                notices.append((index, line))
            continue
        if not any(line.startswith(f"- {handle} ") for handle in WAKE_HANDLES):
            continue
        match = WAKE_PATTERN.match(line)
        if match and match.group("author").strip() == options.author:
            pending.append((index, line))
        else:
            skipped.append((index, line))
    for index, line in skipped:
        who = WAKE_PATTERN.match(line)
        log(
            f"SKIP line#{index} 署名不是「{AUTHOR}」"
            f"（{who.group('author').strip() if who else '解析失败'}）：{line[:60]}"
        )
    cold = state.get("last_index") is None

    today = dt.date.today().isoformat()
    if state.get("day") != today:
        state["day"] = today
        state["day_count"] = 0
    remaining = max(0, DAILY_CAP - int(state.get("day_count", 0)))

    log(
        f"RUN mode={mode} lines={len(lines)} start={start} "
        f"pending={len(pending)} notices={len(notices)} today={state['day_count']}/{DAILY_CAP}"
    )

    if cold:
        log(f"COLD-START 只记不发（尾部 {len(lines)} 行）")

    sent = 0
    notice_sent = 0
    # 公告**不按铃**（老板 2026-09-11 02:1x：让他下次露面时把回执带回来就行）。
    # 这里只记账：有公告待回执时，本轮若有 @dsh 唤醒，就在提示里顺手提醒它带上回执。
    pending_notice = last_notice_line(lines)
    for index, line in pending:
        if cold:
            break
        if sent >= remaining:
            log(f"CAP 命中每日上限 {DAILY_CAP}，剩余 @dsh 行留到明天（不丢，会顺延）")
            break
        if options.dry_run:
            log(f"DRYRUN would wake line#{index}: {line[:80]}")
            print(f"would wake line#{index}: {line[:80]}")
            sent += 1
            continue
        try:
            text = wake_text(line)
            if pending_notice:
                text = text + "\n\n" + notice_text(pending_notice)
            result = post_prompt(text, options.session)
            ok = bool(result.get("result", {}).get("ok"))
            log(f"WAKE line#{index} ok={ok} {json.dumps(result, ensure_ascii=False)[:200]}")
            if ok:
                sent += 1
                state["day_count"] = int(state.get("day_count", 0)) + 1
            else:
                fallback(line, f"rpc-not-ok: {json.dumps(result, ensure_ascii=False)[:120]}")
        except Exception as error:  # noqa: BLE001 — 任何异常都要留痕并兜底
            log(f"ERROR line#{index} {error!r}")
            fallback(line, repr(error)[:200])
        # 同一次运行里多条 @dsh 只叫醒一次就够：后续行随下次运行处理
        break

    state.update(
        {
            "last_index": len(lines),
            "last_hash": line_hash(lines[-1]) if lines else None,
            "last_run": dt.datetime.now().isoformat(timespec="seconds"),
        }
    )
    save_state(state)
    if sent:
        print(f"woke {sent}")
    if notice_sent:
        print(f"notice-informed {notice_sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
