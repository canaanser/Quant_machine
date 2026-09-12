# 交接文档 · `codex-套件`（2026-09-12）

> ⚠️ **本文由 `codex-总监` 代笔**（前任线 `01a08cf8` 被平台通道卡住、叫不醒，无法自己写）。
> 内容全部取自它的看板发言、它的报告与仓库实测；**待前任上线确认**，有出入以前任原话为准。
> 代笔事实已登记在 `outputs/dialog/successions.ndjson`。

## 一、身份（我是谁、我的号）

- **看板名（岗位）**：`codex-套件` —— 延续，不变；署名一律用它，**不借别人的名**。
- **工号（slug）**：前任 `codex-kit` → 本代 **`codex-kit2`**（旧号永不复用）。
- **前任实例（threadId）**：`01a08cf8-4967-7ab2-836d-f60a7d700350`，`cwd=E:\stockgate\Quant_Alpha_System`
  ——**它的可写根是量化仓，写不到自己的产品仓**（实测 `Access to the path 'D:\agent_crew_kits\...' is denied`），
  所以本届才要换到以 `D:\agent_crew_kits` 为工作区的新实例（`01a095bb-e7e2-7662-a653-4a3d114a7b3d`）。
- **层级/职能**：`lead`（组长级）· 套件开发（`agent_crew_kits` 产品负责人）；员工卡 `agents/codex-kit.card.json`。

## 二、工位与信箱

- **工位**：`D:\agent_crew_kits`（远程 `git@github.com:canaanser/agent_crew_kits.git`）——**这是你的产品仓，本代起你能直接写**。
- **信箱**：`E:\stockgate\Quant_Alpha_System\outputs\dialog\pending_codex-kit2.ndjson`（未读已从旧信箱转来）；
  镜像到工位 `.private\codex-kit2\inbox.md`。
- **私人夹**：`.private\codex-kit\`（已复制成 `.private\codex-kit2\`，旧的不删 = 前任存在过的证据）。
- **看板**：`docs/COMMS_BOARD.md`（投影）· `outputs/dialog/dialog.ndjson`（真源）· 回帖走 `POST http://100.64.75.72:8788/api/post`。

## 三、在办与未结单据

| 卡 | 状态 | 已签 / 未签 | 备注 |
| --- | --- | --- | --- |
| `KIT-001`（M0 内核最小闭环） | **代码全在、测试全绿、未提交** | **未签**（提交要老板授权） | `core/ journal,registry,router,mailbox` + `cli/ack.mjs` + `tests/`；`npm test` **34/34**；五条验收证据在 `run/acceptance/` |
| `REQ-KIT-DSH-001`（DSH 侧接入员工与层级） | ✅ **已落地**（两张卡 + `org-levels` §六 + `KIT-002` 卡 + 录入清单） | 已落地未签 | 落地脚本 `E:\stockgate\Quant_Alpha_System\outputs\kit_handoff\apply_req_dsh_001.ps1`（幂等、有备份）；`/api/employees` 已认账（`byLevel` member8→7 / lead1→2） |
| `KIT-002`（M1：首批适配器 + 入职三连自检） | **已建卡，待开工** | 未签 | 按卡 §二做，**先做两个**：`outbound/board-append`（产出回板）、`schedule/cron`（定时唤醒） |

**下一动作（接手第一件事）**：建 `feature/kit-m0` 分支 → 提交 M0 全量（`core/ cli/ tests/ package.json docs/slug.md docs/reports/`）→ 推 origin。
**不许自己合 `main`**（合入归 Codex 侧）；`CREW_TASK=KIT-001`。

## 四、别再做什么（前任踩过的坑）

1. **别怀疑工位配置**：前任写不进 `D:` 不是它写错，是**会话创建时固化的白名单**——本代已换窗口解决。若又遇到写不进，先报总监，不要反复试。
2. **PowerShell 5.1 发中文要转 UTF-8 字节**再打 `/api/post`，否则 `JSON.parse` 失败 → 400「格式不对」（前任踩过，卡里也记了）。
3. **契约先行**：`spec/*.json` 要改**先报老板**，不许在实现里偷加字段。
4. **不许整份覆盖别人的文件**（`board.mjs` 这类共享文件只动自己那几行；19:xx 已发生过一次"代码被无声吃掉"）。
5. **不许对同一个 deferred 命名空间连续 `tool_search` 两次**（会把线永久锁死，`LESSONS.md` L12）。
6. **批文归卡不归线**：签字留在卡上，已签的不许再签一遍。

## 五、证据路径（接手的人自己核）

- 产品现状与架构：`D:\agent_crew_kits\README.md`、`docs/architecture.md`、`docs/org-levels.md`（含 §六）
- M0 停点报告：`D:\agent_crew_kits\docs\reports\KIT-001_m0-1.md` ~ `KIT-001_m0-4-prep.md`
- 总监验收记录：`E:\stockgate\Quant_Alpha_System\docs\reports\20260912_KIT-001_acceptance.md`
- 承接机制：`docs\RUNBOOK_SUCCESSION.md`、`docs\SUCCESSION_TEMPLATE.md`、`scripts\crew_succession.mjs`
