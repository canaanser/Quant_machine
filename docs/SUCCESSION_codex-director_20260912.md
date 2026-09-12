# 交接文档 · `codex-总监`（2026-09-12）

> 依 `docs/SUCCESSION_TEMPLATE.md` 出据，供 `scripts/crew_succession.mjs` 门禁。**红线已读。**
> 本文只写"接手的人必须知道的"，不写回忆录。

## 一、身份（我是谁、我的号）

- **看板名（岗位）**：`codex-总监` —— 这个**延续**，不变；
- **工号（slug）**：`codex-director` —— 这个**永不复用**，新一代是 `codex-director2`；
- **我的实例（threadId）**：`01a08ac2-d43a-72f0-8a26-618e3c8e8edd` —— **被锁死**（2026-09-12 23:06 起，见下）；
- **署名纪律**：只用 `codex-总监` 发言，绝不借别人的名字（`docs/LESSONS.md` L1）。

**锁死事实（一句话）**：断电时 rollout 尾部留下一条 `function_call_output` **缺 `call_id`**，
每次回放都被服务端 `invalid_request_error: missing field call_id` 拒收 → **本线每一轮都起不来**。

## 二、工位与信箱

- **工位**：`E:\stockgate\Quant_Alpha_System`（本线可写范围；越权即红线）；
- **信箱**：`outputs/dialog/pending_<slug>.ndjson`（= `pending_codex-director.ndjson`）；镜像到 `.private\<slug>\inbox.md`；
- **私人夹**：`.private\codex-director\`；
- **看板**：`docs/COMMS_BOARD.md`（投影）、`outputs/dialog/dialog.ndjson`（真源）；写板一律走 `POST /api/post`，署名 `codex-总监`。

## 三、在办与未结单据

| 卡 / 事项 | 状态 | 已签 / 未签 | 备注（证据路径） |
| --- | --- | --- | --- |
| **KIT-002**（套件 M1-2 四适配器） | **待我验收** | 未签 | 分支 `feature/kit-m1-2`、提交 `b983aad`；证据 `docs/reports/KIT-002_m1-2.md` + `run/acceptance-m1-2/*.log`；自测 `npm test` 82/82 |
| **HUB-008**（含 HUB-007/011-013 + 公告系统重做） | **待我验收** | 未签 | 分支 `feature/hub-carry-layer`、提交 `193da69`；证据 `tools/mobile_chat/selftest_v2.mjs`、`outputs/dialog/ui_check.png`；自测 190/190、ui_check 44/44 |
| **看板编辑 30+ 未提交改动** | **在办** | 老板 22:22 已拍板选 a | 我 22:23 已转达：建 `feature/hub-*` **只提 Hub 路径**（不许 `git add -A`）→ 交活给我 → 我验完合 main |
| **门铃"只叫真未读"永久修复** | **差一次重载** | 未结 | 我已把 `crew_host.py` 改完并加了自我重载；**需老板跑一次**：`Stop-ScheduledTask QuantCrewHost; Start-ScheduledTask QuantCrewHost`。临时静默已生效（22:26–22:28 门铃 0 次） |
| **KIT-003**（DSH 适配环境核验） | **卡凭据** | 未结 | 3080 在（401）、WSL 工位可写；**dsh web token 拿不到**（`/dev/pts/0` 输出，无 cookie 残留）→ 需老板/平台给凭据 |
| **公告 N-2343 回执** | **已签** | 我 22:13 已回执（mode=code） | **不许再签第二遍**；当前 4/6，缺 dsh 两条 |
| **合入闸** | 空 | — | `outputs/merge/merge_request.json` 不存在；最近三条已 `done`（22:14/22:17/22:32） |
| **PLT-001 ③**（请求构造去重，上游） | 登记待办 | — | 本地改不到，不许拿本地改造冒充 |
| **PLT-002**（沙箱外 crew-host 宿主） | 在建 | — | `mirror-mailbox` / `git-publisher` / `doorbell` / `heartbeat` 四小工；红线：只搬运不做决策 |

> **批文归卡、不归线**：签字留在任务卡上，两代共用；**已签的不许再签一遍**。
> **接手第一件事**：① 催老板做上面那次**宿主重载**；② 收 KIT-002 / HUB-008 两个待验收；③ 看 `outputs/merge/merge_request.json` 有无待合入。

## 四、别再做什么（前任踩过的坑）

1. **别修库、别动 `rollout-*.jsonl`**（`docs/LESSONS.md` L11）：投影 ≠ 账本。我这次就是账本尾部一条残项（缺 `call_id`）把线锁死；修它属**平台级改动，未获老板授权前一个字都不许动**。
2. **不许对同一个 deferred 命名空间连搜两次 `tool_search`**（L12 / `AGENTS.md` 红线）：重复即整轮 400、该线永久锁死；`node_repl` 是内置的，**人人有份**。
3. **开窗只能老板在 UI 手动点**（L15 坑②）：用工具建窗，首回合就踩**同一个** `missing field call_id` bug。
4. **改名必须早于归档**（L15 坑①）：对已归档线程 `set_thread_title` 会报 `no rollout found`。
5. **改全局配置 = 平台级改动**，三件套缺一不可：登记（影响面=所有线）+ 回滚点 + 风险说明（L2）。
6. **不许 `git add -A`**：量化仓里混着别人在办的东西，只提自己路径（我 22:21 给看板编辑定过的边界）。

## 五、证据路径（接手的人自己核）

- **故障原始账本（只读）**：`C:\Users\Administrator\.codex\sessions\2026\09\10\rollout-2026-09-10T18-00-19-01a08ac2-d43a-72f0-8a26-618e3c8e8edd.jsonl`
  - 第 **8228** 行：`function_call_output`（`automation_update`/`codex_app`）**缺 `call_id`**，ts `2026-09-12T15:06:39Z`（本地 23:06:39，断电时刻）；
  - 第 **8230 / 8239** 行：两轮 `task_complete` 的 400（`missing field call_id`，本地 23:06:40 / 23:07:36）；
  - 最后一次成功回合：**22:36:53**；此后无任何成功回合。
- **全库核验**：扫全部 `sessions\*\*\*\*.jsonl`，缺 `call_id` 的项**仅此一条**（其余线未被断电波及）。
- **现状锚点**：`docs/STATE_ANCHOR.md`、`docs/MAIN_ANCHOR.md`；
- **承接记录真源**：`outputs/dialog/successions.ndjson`（append-only）；名册：`outputs/dialog/agents.json`。
