# 文档索引（一页找东西）

> **用途**：让"翻文件"变成"读一页"。**每份文档一行：路径 → 一句话（结论/用途）**。
> 维护：`codex-总监`；**新增文档必须在这里加一行**（否则等于没写）。
> 约定（`AGENTS.md` 减法续六条 §8）：**报告头 5 行摘要**才是别人要读的，正文是证据。

## 一、规约（真源，只在这里写全文）

| 路径 | 一句话 |
| --- | --- |
| `AGENTS.md` | **唯一规约真源**（每轮自动加载）：角色/层级、过程播报、**裁决阶梯**、**派活链路**、**老板面纪律**、**P0 老板优先**、**减法五条/续六条**、发送与叫醒、红线 |
| `docs/READING.md` | 必读矩阵（全局 + 三层）；**开工只读 AGENTS.md + `whoami`**，其余按需 |
| `docs/ORG_CHART.md` | 组织关系链 + 谁能派谁（**细则见 AGENTS.md**，本页只留指针） |
| `docs/TASK_ID_STANDARD.md` | 卡号前缀表与取号纪律（前缀＝领域，不按组织；`CT/RV/AR/OP` 冻结） |
| `docs/LESSONS.md` | 教训账本 L1–L31（每条：事件→后果→变成什么规矩） |
| `docs/RUNBOOK_COMMIT_GATE.md` | **提交闸**（署名必须实名看板名 / 不许在别人分支提交）+ 共用工作树的正确用法（`-c` 具名）+ 回滚一行 |
| `docs/DIALOG_HUB.md` | 看板/Hub 的口径与运维（含 §十九 重启与授权） |

## 二、今晚（2026-09-13）的报告 —— 按"读头 5 行就够"排

| 路径 | 一句话 |
| --- | --- |
| `docs/reports/20260913_recent_chaos_stats.md` | **"重复门铃"四类来源 + 根因 + 修法**（老板 N-26ED 交办的那份统计） |
| `docs/reports/20260913_two_channels_merge.md` | 两条叫醒通道合一（共用账本 `pushed.ndjson`）+ 上线三次回修 |
| `docs/reports/20260913_p0_boss_priority.md` | 老板优先 P0 通道（排序最前/限流豁免/提示语带标记） |
| `docs/reports/20260913_joinedAt_ruling.md` | `joinedAt` 裁定与 15 条取值（修复线 = 09-13 01:44，原 `17:44` 是 UTC 混写） |
| `docs/reports/20260913_计划任务清单.md` | 本机 12 条计划任务（干什么/触发/归谁/怎么停）；**9 条归量化线、3 条平台线** |
| `docs/reports/BRIEF_quant_20260913.md` | 给量化总监的**总交底**（现状 + 全部移交项 + 时间线） |
| `docs/reports/HANDOVER_quant_20260913.md` | 量化移交清单（单子/边界/材料/收回"派活"那层） |
| `docs/reports/HUB-018_review.md` / `PLT-006_review.md` / `PLT-007_gate.md` / `TRD-003_gate.md` | 我跑过的**门禁记录**（各 7 条判据 + 结论） |
| `docs/reports/SUCCESSION_*` / `docs/tasks/PLT-*.md` | 承接档案 / 平台系列卡（**PLT-004 计划任务 · 005 能力门禁 · 006 裁决阶梯 · 007 事件注入**） |

## 三、运行态真源（不是文档，但找东西时先看这里）

| 路径 | 一句话 |
| --- | --- |
| `outputs/dialog/dialog.ndjson` | **看板真源**（append-only） |
| `outputs/dialog/agents.json` | **名册**（level/leader/gender/joinedAt/displayAliases；只读投影） |
| `outputs/dialog/pending_<slug>.ndjson` | 各线**信箱真源**（机器读这里；人看 `.private/<slug>/inbox.md` 镜像） |
| `outputs/dialog/pushed.ndjson` | **叫醒账本**（一封一行；`by=hub/crew_host`；`mailbox_ts` 判水位） |
| `outputs/crew_host_log.txt` | 小工日志（门铃行带 `ts/n/lvl/h` 判据字段） |
| `outputs/merge/merge_request*.json` | 门禁产物（含**证据指纹**：cmd/code/head/sha256/日志路径） |
