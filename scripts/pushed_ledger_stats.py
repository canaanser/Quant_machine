#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""只读统计推送账本 `outputs/dialog/pushed.ndjson` 的键空间分布（PLT-006）。

为什么要有它：账本里 `to` 字段**混用两套键**（slug 与看板名）——
任何"按收件线查账本"的逻辑若不归一，就会漏掉另一半（补投查询正是漏的那一端）。

用法：python scripts/pushed_ledger_stats.py
输出：总行数 / 按 (by,to) 分组 / `to` 是否 slug 的统计 / 空 mailbox_ts 行
"""
import collections
import json
import re

SRC = r"E:\stockgate\Quant_Alpha_System\outputs\dialog\pushed.ndjson"
SLUG_RE = re.compile(r"^(?:codex|dsh)-[a-z0-9-]+$")  # 小写连字符 = slug；含中文 = 看板名


def main():
    rows = []
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    print("账本：%s" % SRC)
    print("总行数：%d" % len(rows))

    print("\n== 按 (by, to) 分组 ==")
    c = collections.Counter((r.get("by"), r.get("to")) for r in rows)
    for (by, to), n in sorted(c.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        kind = "slug " if SLUG_RE.match(str(to or "")) else "看板名"
        print("  by=%-10s to=%-18s x%-3d [%s]" % (by, to, n, kind))

    print("\n== `to` 键形态 ==")
    for by in ("crew_host", "hub"):
        sub = [r for r in rows if r.get("by") == by]
        slug = sum(1 for r in sub if SLUG_RE.match(str(r.get("to") or "")))
        print("  by=%-10s 共 %-3d 行：slug %-3d / 看板名 %-3d"
              % (by, len(sub), slug, len(sub) - slug))

    print("\n== `mailbox_ts` 为空的行（进不了水位判定）==")
    empty = [r for r in rows if not str(r.get("mailbox_ts") or "").strip()]
    print("  共 %d 行" % len(empty))
    for r in empty[-5:]:
        print("   %s" % r)


if __name__ == "__main__":
    main()
