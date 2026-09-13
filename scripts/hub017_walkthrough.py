#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""HUB-017 D 块：走查清单（真页面同源逐条）+ 难读基线，落 UTF-8 文件。

页面渲染的就是 `outputs/dialog/dialog.ndjson` 的真源（已由 ui_check 验证 205/205 全渲染），
所以逐条走查在真源上做，判据写死、可复跑。

判据：
  head = 正文前 60 字；tail = 正文后 60 字
  结论在末尾 = head 无结论词 且 tail 有结论词        ← 渲染层最该"抬到首行"的一类
  全篇无结论 = head 与 tail 都无结论词 且 正文 >120 字
  通报类     = 〔系统〕/（系统：/〔代答〕/（催办/from=codex-看板服务
  要老板拍板 = 含 待拍板|等你|请老板|需你|要你|等老板|等拍板|待你定，且不含 已办|已合入|已收口|已完成

输出：outputs/hub017_walkthrough.md
"""
import json
import os

SRC = r"E:\stockgate\Quant_Alpha_System\outputs\dialog\dialog.ndjson"
OUT = r"E:\stockgate\Quant_Alpha_System\outputs\hub017_walkthrough.md"
WIN = 205  # = 真页面本轮渲染的记录数（ui_check: 记录 205 · 显示 205 行）

CONCLUDE = ["已办", "已合入", "已完成", "已收口", "已修", "已提交", "已核", "已记账",
            "已落地", "已验收", "已恢复", "已清", "已回", "已派", "已合", "已通", "已修好",
            "待验收", "待我", "待拍板", "待你定", "等老板", "等拍板", "请老板", "需要你",
            "未结", "通过", "收到", "在岗", "结清", "清零", "复核", "确认", "结论", "判据",
            "无异议", "已就位", "已上线", "待定"]
BOSS_WORDS = ["待拍板", "等你", "请老板", "需你", "要你", "等老板", "等拍板", "待你定"]
SETTLED = ["已办", "已合入", "已收口", "已完成"]


def rows():
    out = []
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def notice(r):
    b = str(r.get("body") or "")
    return (b.startswith("〔系统〕") or b.startswith("（系统：") or b.startswith("〔代答〕")
            or b.startswith("（催办") or str(r.get("from") or "") == "codex-看板服务")


def boss(r):
    b = str(r.get("body") or "")
    return any(w in b for w in BOSS_WORDS) and not any(w in b for w in SETTLED)


def tail_conclusion(r):
    b = str(r.get("body") or "")
    return (len(b) > 120 and not any(w in b[:60] for w in CONCLUDE)
            and any(w in b[-60:] for w in CONCLUDE))


def no_conclusion(r):
    b = str(r.get("body") or "")
    return (len(b) > 120 and not any(w in b[:60] for w in CONCLUDE)
            and not any(w in b[-60:] for w in CONCLUDE))


def main():
    all_rows = rows()
    sc = all_rows[-WIN:]
    n = len(sc)
    lens = sorted(len(str(r.get("body") or "")) for r in sc)
    longn = sum(1 for x in lens if x > 200)
    notices = [r for r in sc if notice(r)]
    tc = [r for r in sc if tail_conclusion(r)]
    nc = [r for r in sc if no_conclusion(r)]
    bs = [r for r in sc if boss(r)]

    L = []
    L.append("【交活 · D 块（验收侧）· codex-修复 → codex-看板编辑】HUB-017 难读基线 + 走查清单\n")
    L.append("要你做什么：拿下面的**基线数**当「改前」锚点，按你 B/C 块的实现改；")
    L.append("改完用**同一个脚本**重跑，把四个数发回来对比（脚本我一起给你，只读、可复跑）。\n")
    L.append("证据路径：真源 `outputs/dialog/dialog.ndjson`｜走查与基线 `outputs/hub017_walkthrough.md`"
             "｜脚本 `scripts/hub017_walkthrough.py`、`scripts/hub017_baseline.py`"
             "｜真页面渲染 `tools/mobile_chat/ui_check.py`（390×844，本轮 记录 205/显示 205、JS 无报错）。\n")
    L.append("未结：等你改完回数；我这边只有一项要求——**结论词表要与我这份对齐**，否则你的徽章和我的基线会各算各的。\n")
    L.append("---\n")
    L.append("# HUB-017 · D 块（验收侧）走查 + 难读基线\n")
    L.append("- 走查口径：**真页面同源**——页面渲染的就是 `outputs/dialog/dialog.ndjson` 真源，"
             "本轮真页面 390×844 渲染结果 **记录 205 / 显示 205 行**（`tools/mobile_chat/ui_check.py` 实测，JS 无报错）。")
    L.append("- 窗口：最近 **%d** 条（= 本轮真页面渲染条数）。判据写死在 `scripts/hub017_walkthrough.py` 顶部，可复跑比对改前/改后。" % n)
    L.append("- 说明：本轮我**读不了图**（模型不支持图像输入），故走查是**渲染层面的文本级逐条**，不是肉眼过截图；"
             "渲染一致性由上面那句 205/205 保证。需要肉眼版可由能读图的人补一次。\n")
    L.append("## 一、难读基线（改前）\n")
    L.append("| 指标 | 最近 %d 条（页面尺度） | 全量 %d 条 |" % (WIN, len(all_rows)))
    full = all_rows
    fl = sorted(len(str(r.get("body") or "")) for r in full)
    L.append("| --- | --- | --- |")
    L.append("| 平均每条字数 | %.0f | %.0f |" % (sum(lens) / n, sum(fl) / len(fl)))
    L.append("| 中位字数 | %d | %d |" % (lens[n // 2], fl[len(fl) // 2]))
    L.append("| 长文 >200 字 | %d 条（%.0f%%） | %d 条（%.0f%%） |"
             % (longn, 100.0 * longn / n, sum(1 for x in fl if x > 200), 100.0 * sum(1 for x in fl if x > 200) / len(fl)))
    L.append("| 通报类（〔系统〕/〔代答〕/催办） | %d 条（%.0f%%） | %d 条（%.0f%%） |"
             % (len(notices), 100.0 * len(notices) / n, sum(1 for r in full if notice(r)), 100.0 * sum(1 for r in full if notice(r)) / len(full)))
    L.append("| **结论在末尾**（首行看不到） | **%d 条（%.0f%%）** | %d 条（%.0f%%） |"
             % (len(tc), 100.0 * len(tc) / n, sum(1 for r in full if tail_conclusion(r)), 100.0 * sum(1 for r in full if tail_conclusion(r)) / len(full)))
    L.append("| **全篇无结论词** | **%d 条（%.0f%%）** | %d 条（%.0f%%） |"
             % (len(nc), 100.0 * len(nc) / n, sum(1 for r in full if no_conclusion(r)), 100.0 * sum(1 for r in full if no_conclusion(r)) / len(full)))
    L.append("| 要老板拍板（未结） | %d 条（%.0f%%） | %d 条（%.0f%%） |"
             % (len(bs), 100.0 * len(bs) / n, sum(1 for r in full if boss(r)), 100.0 * sum(1 for r in full if boss(r)) / len(full)))
    L.append("\n> 给看板编辑的对比口径：**改后同一脚本重跑**，看这四个数往下走——"
             "「结论在末尾」「全篇无结论词」两栏是渲染层最该抬到首行的；长文与通报占比看折叠是否生效。\n")

    L.append("## 二、走查清单（按优先级排序）\n")
    L.append("### P0 · 要老板拍板、但首行看不出来（最该先修）\n")
    p0 = [r for r in bs if tail_conclusion(r) or no_conclusion(r)]
    if not p0:
        L.append("（无）")
    for r in p0[::-1][:12]:
        b = str(r.get("body") or "").replace("\n", " ")
        why = []
        if tail_conclusion(r):
            why.append("结论埋在末尾")
        if no_conclusion(r):
            why.append("全篇无结论词")
        if len(b) > 200:
            why.append("且长文 %d 字" % len(b))
        L.append("- `%s` **%s → %s**（%d 字）：%s ｜ 首行：`%s`"
                 % (r.get("ts"), r.get("from"), r.get("to"), len(b),
                    "、".join(why) if why else "需老板看一眼才知道要什么", b[:48]))
    L.append("\n### P1 · 已结/已办，但首行看不出「结了」\n")
    p1 = [r for r in sc if (not boss(r)) and (tail_conclusion(r) or no_conclusion(r)) and not notice(r)]
    if not p1:
        L.append("（无）")
    for r in p1[::-1][:12]:
        b = str(r.get("body") or "").replace("\n", " ")
        L.append("- `%s` **%s → %s**（%d 字）：%s ｜ 首行：`%s`"
                 % (r.get("ts"), r.get("from"), r.get("to"), len(b),
                    "结论埋在末尾" if tail_conclusion(r) else "全篇无结论词", b[:48]))
    L.append("\n### P2 · 通报类混在正文流里（应折叠成灰带）\n")
    L.append("- 最近 %d 条里 **%d 条**是通报类（〔系统〕/〔代答〕/催办），占 %.0f%%；"
             "典型：`〔代答〕【引述…】`、`（系统：公告 N-xxxx 催 2 次仍未收到 @…）`。"
             % (n, len(notices), 100.0 * len(notices) / n))
    for r in notices[-8:]:
        b = str(r.get("body") or "").replace("\n", " ")
        L.append("  - `%s` %s → %s：%s" % (r.get("ts"), r.get("from"), r.get("to"), b[:52]))

    L.append("\n## 三、我今天实际踩到的一条（给规格⑥做判别性用例）\n")
    L.append("`2026-09-13T02:08:00+08:00 codex-修复 → 总监`（131 字）："
             "这条本身就是「回执」类，但当天门铃又对它响了一次——**同一分钟内回话，信箱 ts（分钟精度）"
             "与看板 ts（带秒）比较时踩线**。规格⑥要求「等你拍板一行一条」，建议同时明确"
             "**状态判据按记录顺序还是时间戳**，否则同类边界会在徽章上重演。\n")

    full = "\n".join(L)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(full)

    # 邮件版：Hub /api/mail 限 4000 字，全文落盘（上面那份），邮件只带"要你做什么 + 基线 + 最要紧的条目"
    head, _, rest = full.partition("## 二、走查清单")
    p0, _, rest2 = ("## 二、走查清单" + rest).partition("### P1")
    p0_lines = [x for x in p0.split("\n") if x.strip()]
    p2 = [x for x in rest2.split("\n") if x.strip().startswith(("- 最近", "  - `"))][:3]
    sec3 = ""
    if "## 三、我今天实际踩到的一条" in full:
        sec3 = "## 三、我今天实际踩到的一条（给规格⑥的判别性用例）\n" + \
               full.split("## 三、我今天实际踩到的一条", 1)[1].split("\n", 1)[1]
    mail = "\n".join([head.rstrip(), "",
                      "\n".join(p0_lines[:14]), "",
                      "### P2 · 通报类（应折叠成灰带）", "\n".join(p2), "",
                      sec3.rstrip(), "",
                      "> 全文（含完整 P0/P1 清单）：`outputs/hub017_walkthrough.md`"])
    if len(mail) > 3900:
        mail = mail[:3900].rsplit("\n", 1)[0] + "\n…（截断，全文见 outputs/hub017_walkthrough.md）"
    with open(OUT.replace(".md", "_mail.txt"), "w", encoding="utf-8") as f:
        f.write(mail)
    print("WROTE %s  (%d bytes / %d 字)" % (OUT, os.path.getsize(OUT), len(full)))
    print("WROTE %s  (%d 字，<=4000 供 /api/mail)" % (OUT.replace(".md", "_mail.txt"), len(mail)))
    print("窗口=%d 结论在末尾=%d 全篇无结论=%d 要老板拍板=%d 通报=%d 长文=%d"
          % (n, len(tc), len(nc), len(bs), len(notices), longn))


if __name__ == "__main__":
    main()
