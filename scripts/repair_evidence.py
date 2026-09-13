#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PLT-003 修复证据：逐对核「等字节替换」是否成立（前后行数与字节数一致）。

为什么要它：codex-总监 09:44 裁定"修复类写入"若开例外，必须满足
①仅限已锁死的线 ②等字节替换 ③先备份 ④每次报备 —— 老板若批，他要核这份证据。

做法（**只读**）：找出我名下所有 `*.bak-*` 备份，与它对应的**现盘文件**逐对比：
  行数、字节数 是否完全一致；并列出备份里/现盘里各自的残项数（`function_call_output` 缺 `call_id`）。

用法：python scripts/repair_evidence.py
"""
import glob
import json
import os
import re

ROOTS = [r"C:\Users\Administrator\.codex\sessions",
         r"C:\Users\Administrator\.codex\archived_sessions"]


def stat(path):
    if not os.path.exists(path):
        return None
    size = os.path.getsize(path)
    lines = 0
    poison = 0
    with open(path, "rb") as f:
        for raw in f:
            lines += 1
            if b'"function_call_output"' in raw and b'"call_id"' not in raw:
                poison += 1
    return {"size": size, "lines": lines, "poison": poison}


def main():
    OUT = r"E:\stockgate\Quant_Alpha_System\docs\reports\PLT-003_repair_evidence.md"
    rep = []
    baks = []
    for r in ROOTS:
        baks += glob.glob(os.path.join(r, "**", "*.jsonl.bak-*"), recursive=True)
    baks = sorted(set(baks))
    print("找到备份 %d 份" % len(baks))
    rep.append("# PLT-003 修复证据 · 「等字节替换」逐对核验")
    rep.append("")
    rep.append("> 依据：`codex-总监` 09:44 裁定——「修复类写入」若要开例外，须满足"
               "①仅限已锁死的线 ②等字节替换 ③先备份 ④每次报备；本页供老板/总监核。")
    rep.append("> 生成：`python scripts/repair_evidence.py`（只读，不写任何账本）。")
    rep.append("")
    rep.append("| 备份（前） | 线程 | 行数 前→后 | 字节 前→后 | 残项 前→后 | 等字节+等行数 |")
    rep.append("| --- | --- | --- | --- | --- | --- |")
    rows = []
    for b in baks:
        base = re.sub(r"\.bak-.*$", "", b)                 # 去掉 .bak-… 后缀
        cand = [base,
                os.path.join(ROOTS[1], os.path.basename(base)),
                os.path.join(ROOTS[0], os.path.basename(base)),
                base + ".jsonl"]                            # 万一
        cur = next((c for c in cand if os.path.exists(c)), None)
        sb, sc = stat(b), (stat(cur) if cur else None)
        name = os.path.basename(b)
        tid = re.search(r"(01a[0-9a-f-]{10,})", name)
        tid = tid.group(1) if tid else "?"
        print("\n--- %s ---" % name)
        print("  线程 %s" % tid)
        print("  备份：%s" % sb)
        print("  现盘：%s  (%s)" % (sc, cur or "未找到"))
        if sb and sc:
            ok = sb["size"] == sc["size"] and sb["lines"] == sc["lines"]
            print("  等字节+等行数：%s" % ("一致 OK" if ok else "不一致 NG"))
            print("  残项：备份 %d → 现盘 %d" % (sb["poison"], sc["poison"]))
            rows.append((name, tid, ok, sb, sc))
            rep.append("| `%s` | `%s` | %d → %d | %d → %d | %d → %d | %s |"
                       % (name, tid, sb["lines"], sc["lines"], sb["size"], sc["size"],
                          sb["poison"], sc["poison"], "一致" if ok else "**不一致**"))
    ok_all = all(r[2] for r in rows) and rows
    print("\n===== 汇总 =====")
    print("可对照的备份：%d 份；全部满足等字节+等行数：%s" % (len(rows), "是 OK" if ok_all else "否 NG"))
    rep.append("")
    rep.append("**汇总**：可对照 %d 份；全部满足「等字节 + 等行数」：**%s**。"
               % (len(rows), "是" if ok_all else "否"))
    rep.append("")
    rep.append("> 说明：残项列 = 该账本里缺 `call_id` 的 `function_call_output` 行数；")
    rep.append("> 行数/字节数**前后完全一致**，即证明是「就地等长替换」、**没有增删行**（投影的字节偏移不会错位）。")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")
    print("已写证据页：%s" % OUT)


if __name__ == "__main__":
    main()
