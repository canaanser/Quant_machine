#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PLT-003 修复证据（正口径）：**逐行**核"等字节替换"。

为什么不能拿整档比：被修的线若是**活着的**，我修完之后它自己还在往后写
（例：总监线 8879 → 19737 行），整档比较必然"不一致"——那是**后续正常增长**，不是我的写坏。

正确判据：**同一个行号，改前/改后的字节长度必须相等**（行数与总字节在我的那一次写入上不变；
脚本在写入时也做过同断言的"写后核验"）。

用法：python scripts/repair_evidence_lines.py
输出：docs/reports/PLT-003_repair_evidence.md（覆盖为逐行口径版本）
"""
import os

ARCH = r"C:\Users\Administrator\.codex\archived_sessions"
S13 = r"C:\Users\Administrator\.codex\sessions\2026\09\13"
SESS = r"C:\Users\Administrator\.codex\sessions\2026\09\10"
OUT = r"E:\stockgate\Quant_Alpha_System\docs\reports\PLT-003_repair_evidence.md"

# (备份, 现盘, 被替换的行号列表)
CASES = [
    (SESS + r"\rollout-2026-09-10T18-00-19-01a08ac2-d43a-72f0-8a26-618e3c8e8edd.jsonl.bak-plt003-20260912151517",
     SESS + r"\rollout-2026-09-10T18-00-19-01a08ac2-d43a-72f0-8a26-618e3c8e8edd.jsonl", [8228, 8243]),
    (SESS + r"\rollout-2026-09-10T18-00-19-01a08ac2-d43a-72f0-8a26-618e3c8e8edd.jsonl.bak-plt003b-20260912232542",
     SESS + r"\rollout-2026-09-10T18-00-19-01a08ac2-d43a-72f0-8a26-618e3c8e8edd.jsonl", [8228, 8243]),
    (SESS + r"\rollout-2026-09-10T18-00-19-01a08ac2-d43a-72f0-8a26-618e3c8e8edd.jsonl.bak-callid-20260913003259",
     SESS + r"\rollout-2026-09-10T18-00-19-01a08ac2-d43a-72f0-8a26-618e3c8e8edd.jsonl", [8877]),
    (S13 + r"\rollout-2026-09-13T02-34-50-01a096e6-98c2-7c51-b913-8d368e7352cb.jsonl.bak-callid-20260913024250",
     ARCH + r"\rollout-2026-09-13T02-34-50-01a096e6-98c2-7c51-b913-8d368e7352cb.jsonl", [111]),
    (S13 + r"\rollout-2026-09-13T02-35-21-01a096e7-140e-7a60-bb71-c9c23e768acf.jsonl.bak-callid-20260913024251",
     ARCH + r"\rollout-2026-09-13T02-35-21-01a096e7-140e-7a60-bb71-c9c23e768acf.jsonl", [81]),
    (S13 + r"\rollout-2026-09-13T02-35-32-01a096e7-3d86-71a1-ad0c-cffe1735d230.jsonl.bak-callid-20260913024251",
     ARCH + r"\rollout-2026-09-13T02-35-32-01a096e7-3d86-71a1-ad0c-cffe1735d230.jsonl", [84]),
]


def line_bytes(path, n):
    with open(path, "rb") as f:
        for i, raw in enumerate(f, 1):
            if i == n:
                return len(raw.rstrip(b"\n"))
    return None


def main():
    rows = []
    for bak, cur, ordinals in CASES:
        if not (os.path.exists(bak) and os.path.exists(cur)):
            rows.append((os.path.basename(bak), ordinals, None, None, "文件缺失"))
            continue
        for n in ordinals:
            b = line_bytes(bak, n)
            a = line_bytes(cur, n)
            rows.append((os.path.basename(bak), [n], b, a, "一致" if b == a else "**不一致**"))
    ok = all(r[4] == "一致" for r in rows)
    L = ["# PLT-003 修复证据 · 「等字节替换」逐行核验（正口径）", "",
         "> ⚠️ **本文件由 `scripts/repair_evidence_lines.py` 生成/覆盖，请勿在本文件里手写内容**",
         "> （手写授权、签字、口径一律进卡：`docs/tasks/PLT-008.md` §授权登记 / §签字区）。", "",
         "> 口径说明：被修的线**可能是活的**（修完它自己还会往后长，如总监线 8879 → 19737 行），",
         "> 所以**不能拿整档比**。正确判据 = **同一行号，改前/改后字节长度相等**。",
         "> 每次写入时脚本还做过一次断言式「写后核验」（总字节、行数、全文可解析）。", "",
         "| 备份（改前） | 行号 | 字节 改前 | 字节 改后 | 判定 |", "| --- | --- | --- | --- | --- |"]
    for name, ns, b, a, verdict in rows:
        L.append("| `%s` | %s | %s | %s | %s |" % (name, ",".join(map(str, ns)), b, a, verdict))
    L += ["", "**汇总**：%d 条逐行对照，全部「等字节」：**%s**。" % (len(rows), "是" if ok else "否"), "",
          "> 复跑：`python scripts/repair_evidence_lines.py`（只读）。"]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("rows=%d ok=%s" % (len(rows), ok))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
