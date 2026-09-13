#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""HUB-017 D 块（验收侧）：看板"难读"基线量化。

只读 `outputs/dialog/dialog.ndjson`（真源）。所有指标**判据写死在下面**，任何人可复跑比对"改前/改后"。

判据定义（口径写死，避免各说各话）：
  窗口        ：默认最近 200 条（页面尺度）；同时给出最近 24h 与全量，便于横向看。
  长文        ：`len(body) > 200` 字算长文；`>400` 算超长。
  通报类      ：正文以 `〔系统〕`/`（系统：`/`〔代答〕`/`（催办` 开头，或 `from` 是 `codex-看板服务`。
  首行可判性  ：正文前 **60 字**内是否出现**结论词**（下表 CONCLUDE）。
                **不含结论词 且 正文 >120 字** → 记为「首行看不出结论」。
  要老板拍板  ：正文出现 `待拍板|等你|请老板|需你|要你|等老板|等拍板|待你定`，
                且**不含** `已办|已合入|已收口|已完成`（已结的不算）。

用法：python scripts/hub017_baseline.py [窗口条数，默认 200]
"""
import json
import sys

SRC = r"E:\stockgate\Quant_Alpha_System\outputs\dialog\dialog.ndjson"
CONCLUDE = ["已办", "已合入", "已完成", "已收口", "已修", "已提交", "已核", "已记账",
            "待验收", "待我", "待拍板", "待你定", "等老板", "等拍板", "请老板", "需要你",
            "未结", "通过", "收到", "在岗", "结清", "清零", "复核", "确认"]
BOSS_WORDS = ["待拍板", "等你", "请老板", "需你", "要你", "等老板", "等拍板", "待你定"]
SETTLED = ["已办", "已合入", "已收口", "已完成"]


def load():
    rows = []
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def is_notice(r):
    b = str(r.get("body") or "")
    return (b.startswith("〔系统〕") or b.startswith("（系统：") or b.startswith("〔代答〕")
            or b.startswith("（催办") or str(r.get("from") or "") == "codex-看板服务")


def hard_to_read(r):
    b = str(r.get("body") or "")
    head = b[:60]
    return len(b) > 120 and not any(w in head for w in CONCLUDE)


def needs_boss(r):
    b = str(r.get("body") or "")
    return any(w in b for w in BOSS_WORDS) and not any(w in b for w in SETTLED)


def stats(rows, label):
    n = len(rows)
    if not n:
        print("%s: 空" % label)
        return
    lens = sorted(len(str(r.get("body") or "")) for r in rows)
    avg = sum(lens) / n
    med = lens[n // 2]
    longn = sum(1 for x in lens if x > 200)
    very = sum(1 for x in lens if x > 400)
    notices = sum(1 for r in rows if is_notice(r))
    hard = sum(1 for r in rows if hard_to_read(r))
    boss = sum(1 for r in rows if needs_boss(r))
    print("\n== %s（n=%d）==" % (label, n))
    print("  平均每条 %.0f 字 · 中位 %d 字 · 最长 %d 字" % (avg, med, lens[-1]))
    print("  长文 >200 字：%d 条（%.0f%%）｜ 超长 >400 字：%d 条（%.0f%%）" % (longn, 100.0 * longn / n, very, 100.0 * very / n))
    print("  通报类：%d 条（%.0f%%）" % (notices, 100.0 * notices / n))
    print("  **首行看不出结论**：%d 条（%.0f%%）" % (hard, 100.0 * hard / n))
    print("  要老板拍板：%d 条（%.0f%%）" % (boss, 100.0 * boss / n))


def main():
    win = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    rows = load()
    print("真源：%s\n总行数：%d" % (SRC, len(rows)))
    stats(rows, "全量")
    stats(rows[-win:], "最近 %d 条（页面尺度）" % win)
    day = [r for r in rows if str(r.get("ts", "")).startswith("09/13/2026")]
    stats(day, "09-13 当日")

    scope = rows[-win:]
    print("\n== 最近 %d 条里「要老板拍板」的（按时间倒序，最多 12 条）==" % win)
    hit = [r for r in scope if needs_boss(r)]
    for r in hit[-12:][::-1]:
        b = str(r.get("body") or "").replace("\n", " ")
        print("  [%s] %s -> %s :: %s" % (r.get("ts"), r.get("from"), r.get("to"), b[:70]))
    print("\n== 最近 %d 条里「首行看不出结论」的（最多 12 条）==" % win)
    hit2 = [r for r in scope if hard_to_read(r)]
    for r in hit2[-12:]:
        b = str(r.get("body") or "").replace("\n", " ")
        print("  [%s] len=%d %s :: %s" % (r.get("ts"), len(str(r.get("body") or "")), r.get("from"), b[:60]))


if __name__ == "__main__":
    main()
