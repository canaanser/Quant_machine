#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PLT-001 只读勘察：在 thread_history 里定位"重复的 tool_search_output"那一项。

**全程只读**（sqlite 以 mode=ro 打开，绝不写）。
目的：把"到底该删哪一条"查清楚，让"修库 / 换线"这个决定有据可依。

用法：python scripts/plt001_inspect_history.py [线程id前缀]
"""
import os
import sqlite3
import sys

DB = r"C:\Users\Administrator\.codex\thread_history_1.sqlite"
PREFIX = sys.argv[1] if len(sys.argv) > 1 else "01a0877b"
NEEDLE = "mcp__deepseek_harness"


def main():
    if not os.path.exists(DB):
        print("找不到库:", DB)
        return 2
    con = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
    cur = con.cursor()

    tables = [r[0] for r in cur.execute(
        "select name from sqlite_master where type='table' order by name")]
    print("表:", ", ".join(tables))

    for t in tables:
        cols = [c[1] for c in cur.execute("pragma table_info(%s)" % t)]
        if not any(c in cols for c in ("item_json", "payload", "content", "json")):
            continue
        print("\n--- 表 %s 列: %s" % (t, ", ".join(cols)))
        json_col = next(c for c in ("item_json", "payload", "content", "json") if c in cols)
        tid_col = next((c for c in ("thread_id", "conversation_id", "session_id") if c in cols), None)
        id_col = next((c for c in ("id", "item_id", "rowid") if c in cols), "rowid")
        where = "%s like '%%%s%%'" % (json_col, NEEDLE)
        if tid_col:
            where += " and %s like '%s%%'" % (tid_col, PREFIX)
        try:
            rows = list(cur.execute(
                "select %s, %s, length(%s) from %s where %s order by %s" %
                (id_col, json_col, json_col, t, where, id_col)))
        except Exception as e:
            print("  查询失败:", e)
            continue
        print("  命中 %d 条（含该命名空间）" % len(rows))
        for i, (rid, js, ln) in enumerate(rows):
            head = (js or "")[:160].replace("\n", " ")
            print("   [%d] id=%s len=%s  %s" % (i, rid, ln, head))
        if len(rows) >= 2:
            print("  >>> 前两条即“重复发现”；按裁决应删**后出现的那一条**（保留第一条）")

    print("\n================ 扩大勘察（只读） ================")
    for t in ("thread_items", "thread_realtime_items"):
        try:
            n = cur.execute("select count(*) from %s" % t).fetchone()[0]
            tids = cur.execute(
                "select thread_id, count(*) c from %s group by thread_id order by c desc limit 6" % t).fetchall()
        except Exception as e:
            print(t, "读取失败:", e)
            continue
        print("\n表 %s：共 %d 行；按线程前 6：" % (t, n))
        for tid, c in tids:
            mark = "  <== 目标线" if str(tid).lower().startswith(PREFIX.lower()) else ""
            print("   %s  %d 行%s" % (tid, c, mark))
        for needle in ("deepseek", "tool_search", "toolSearch"):
            try:
                c = cur.execute(
                    "select count(*) from %s where item_json like '%%%s%%'" % (t, needle)).fetchone()[0]
            except Exception:
                c = -1
            print("   含 '%s' 的行数: %s" % (needle, c))

    print("\n================ 目标线 item_type 分布 + tool_search 抽样 ================")
    try:
        dist = cur.execute(
            "select item_type, count(*) c from thread_items where thread_id like ? "
            "group by item_type order by c desc limit 12", (PREFIX + "%",)).fetchall()
        print("item_type 分布（前 12）：")
        for it, c in dist:
            print("   %-28s %d" % (it, c))
        rows = cur.execute(
            "select item_id, item_type, substr(item_json,1,240) from thread_items "
            "where thread_id like ? and item_json like '%tool_search%' order by item_id limit 6",
            (PREFIX + "%",)).fetchall()
        print("\n含 tool_search 的抽样（%d 条抽样）：" % len(rows))
        for iid, it, js in rows:
            print("   [%s] %s  %s" % (it, iid, (js or "").replace("\n", " ")[:180]))
    except Exception as e:
        print("抽样失败:", e)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
