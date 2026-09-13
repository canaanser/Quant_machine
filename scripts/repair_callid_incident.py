#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用修复器：账本/投影里的"缺 call_id 的 function_call_output"残项。

病症：平台把心跳注入写成了一条缺 `call_id` 的 `function_call_output` →
      服务端 `invalid_request_error: missing field call_id` → 该线程**每轮 400**。
做法：账本侧"等字节长度替换"（不增删行、总字节不变，投影里的字节偏移不错位），
      投影侧把对应的 `functionCallOutput` 行同步改成合法 `userMessage`；
      正文一律换成**中性留痕**（明确无需执行），避免它被当成待办去跑。

用法：
  python scripts/repair_callid_incident.py --rollout <rollout.jsonl> --thread <uuid>            # 演练
  python scripts/repair_callid_incident.py --rollout <rollout.jsonl> --thread <uuid> --apply    # 真改（先备份）
"""
import datetime
import json
import sqlite3
import sys

DB = r"C:\Users\Administrator\.codex\thread_history_1.sqlite"
BAD_TYPES = ("function_call", "function_call_output", "custom_tool_call",
             "custom_tool_call_output", "local_shell_call",
             "tool_search_call", "tool_search_output")


def opt(name, default=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else default


APPLY = "--apply" in sys.argv


def main():
    rollout = opt("--rollout")
    thread = opt("--thread")
    if not rollout or not thread:
        print("用法: --rollout <jsonl> --thread <uuid> [--apply]")
        return 2
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    note = ("[修复留痕] 心跳注入项因平台缺陷写入残缺（缺 call_id），已于 %s 就地修复。"
            "此条仅为留痕，无需执行任何动作。" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

    with open(rollout, "rb") as f:
        raw = f.read()
    starts = [0]
    for i, b in enumerate(raw):
        if b == 10:
            starts.append(i + 1)

    poison = []
    for li in range(len(starts)):
        s = starts[li]
        e = starts[li + 1] - 1 if li + 1 < len(starts) else len(raw)
        if e <= s:
            continue
        try:
            o = json.loads(raw[s:e].decode("utf-8"))
        except Exception:
            continue
        p = o.get("payload") or {}
        if o.get("type") == "response_item" and p.get("type") in BAD_TYPES and not p.get("call_id"):
            poison.append({"line": li + 1, "s": s, "len": e - s, "obj": o})

    # 投影里的残项行（账本可能已修过，但库里那行还没同步）
    con0 = sqlite3.connect(DB)
    con0.row_factory = sqlite3.Row
    db_rows = con0.execute(
        "select item_id, item_json, rollout_ordinal from thread_items "
        "where thread_id = ? and item_type = 'functionCallOutput' order by rollout_ordinal",
        (thread,)).fetchall()
    con0.close()
    if not poison and not db_rows:
        print("OK 账本与投影都没有残项。")
        return 0
    if not poison:
        print("注意：账本已无残项，但投影还有 %d 行待同步。" % len(db_rows))

    plan = []
    for it in poison:
        p = it["obj"]["payload"]
        new = {
            "timestamp": it["obj"]["timestamp"],
            "ordinal": it["obj"].get("ordinal"),
            "type": "response_item",
            "payload": {
                "type": "message",
                "id": "msg_" + str(p.get("id", "repaired")).replace("fco_", ""),
                "role": "user",
                "content": [{"type": "input_text", "text": note}],
            },
        }
        if p.get("internal_chat_message_metadata_passthrough"):
            new["payload"]["internal_chat_message_metadata_passthrough"] = \
                p["internal_chat_message_metadata_passthrough"]
        body = json.dumps(new, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > it["len"]:
            print("X 第 %d 行：替身(%dB) 比原文(%dB) 长，拒绝执行" % (it["line"], len(body), it["len"]))
            return 3
        body += b" " * (it["len"] - len(body))
        plan.append((it["line"], it["s"], body, p.get("id")))

    print("== 账本 ==")
    print("  %s" % rollout)
    print("  总字节 %d / 总行 %d / 残项 %d 条（替换后前两项不变）" % (len(raw), len(starts), len(plan)))
    for line, s, body, iid in plan:
        print("  L%d %s -> 中性留痕" % (line, iid))

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = cur.execute(
        "select item_id, item_json, rollout_ordinal from thread_items "
        "where thread_id = ? and item_type = 'functionCallOutput' order by rollout_ordinal",
        (thread,)).fetchall()
    print("== 投影 ==")
    print("  该线程 functionCallOutput 行数 = %d" % len(rows))
    for r in rows:
        print("  ordinal=%s id=%s" % (r["rollout_ordinal"], r["item_id"]))
    unprojected = [p for p in plan if not any(r["item_id"] == p[3] for r in rows)]
    for p in unprojected:
        print("  （L%d 尚未投影进库；账本已修，之后投影会读到修好的版本）" % p[0])

    if not APPLY:
        print("\n（演练结束；要真改加 --apply）")
        con.close()
        return 0

    bak_roll = "%s.bak-callid-%s" % (rollout, stamp)
    bak_db = "%s.bak-callid-%s" % (DB, stamp)
    with open(bak_roll, "wb") as f:
        f.write(raw)
    data = bytearray(raw)
    for line, s, body, iid in plan:
        data[s:s + len(body)] = body
    with open(rollout, "wb") as f:
        f.write(bytes(data))
    cur.execute("vacuum into ?", (bak_db,))
    for r in rows:
        item = {
            "type": "userMessage",
            "id": r["item_id"],
            "clientId": json.loads(r["item_json"]).get("clientId"),
            "content": [{"type": "text", "text": note}],
        }
        cur.execute("update thread_items set item_json = ?, item_type = 'userMessage' "
                    "where thread_id = ? and item_id = ?",
                    (json.dumps(item, ensure_ascii=False), thread, r["item_id"]))
    con.commit()

    with open(rollout, "rb") as f:
        after = f.read()
    s2 = [0]
    for i, b in enumerate(after):
        if b == 10:
            s2.append(i + 1)
    left = cur.execute(
        "select count(*) from thread_items where thread_id = ? and item_type = 'functionCallOutput'",
        (thread,)).fetchone()[0]
    problems = []
    if len(after) != len(raw):
        problems.append("账本总字节变了 %d -> %d" % (len(raw), len(after)))
    if len(s2) != len(starts):
        problems.append("账本行数变了 %d -> %d" % (len(starts), len(s2)))
    if left:
        problems.append("投影仍有 %d 行 functionCallOutput" % left)
    con.close()

    print("\n备份（账本）：%s" % bak_roll)
    print("备份（投影）：%s" % bak_db)
    if problems:
        print("X 核验不过：\n  - " + "\n  - ".join(problems))
        return 4
    print("OK 账本 %d 条已换中性留痕（总字节/行数不变）；投影 %d 行同步。" % (len(plan), len(rows)))
    print("回滚：Copy-Item '%s' '%s' -Force ; Copy-Item '%s' '%s' -Force（后者需先关 app）"
          % (bak_roll, rollout, bak_db, DB))
    print("提醒：盘上改完还要**重启 Codex app** 才会被重新加载。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
