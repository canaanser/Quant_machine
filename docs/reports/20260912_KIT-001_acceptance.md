# 套件线验收（KIT-001 M0 + REQ-KIT-DSH-001）· codex-总监

日期：2026-09-12 19:5x　验收人：`codex-总监`（L1 审阅）　被验：`codex-套件`（lead）
依据：老板 19:52 看板指令「验收一下套件的进度，指导他继续开发」

## 一、结论

**通过。M0 内核可运行、DSH 四件已落地、App 已即时认账。** 差一件：M0 的代码还没进 git（全是 untracked）。

## 二、我实跑的验收（不是转述它自报）

| # | 验什么 | 怎么验 | 结果 |
| --- | --- | --- | --- |
| 1 | M0 内核测试 | 在 `D:\agent_crew_kits` 跑 `node --test` | **34/34 通过**（0 失败、1.86s） |
| 2 | REQ-KIT-DSH-001 落地 | 跑它自己写的 `outputs\kit_handoff\apply_req_dsh_001.ps1` | **全绿：4 件到位**；备份落 `run\kit-handoff-backup\20260912-195345` |
| 3 | 卡片契约 | 对 `spec/agent-card.schema.json` + `capability-manifest.schema.json` 逐字段核 | 两张卡**缺必填 0、契约外字段 0、能力枚举越界 0** |
| 4 | 落地是否真被系统认 | `GET /api/employees` | `byLevel` 从 `{member:8, lead:1}` → **`{member:7, lead:2}`**；`dsh-老员工`=lead+persona+6 slots，`dsh-quant`=headless+persona+3 slots |

落地脚本我逐行读过再跑：幂等、追加前先备份、不碰 git、不删文件、跑完自查并打印回滚点 —— 符合"改别人工位要留回滚点"的要求。

## 三、还差什么（不给"全绿"的理由）

1. **M0 交付没进版本库**：`cli/`、`core/`、`tests/`、`package.json`、`docs/slug.md`、`docs/reports/` 全是 **untracked**；HEAD 还停在 `ef1cb52`（KIT-010）。
   → 这是**最大风险**：现在这套内核只存在于这台机的一个目录里，机器出事就没了，也谈不上"可移植"。
2. **Codex 侧 6 条线仍无员工卡**：`/api/employees` 里 `codex-唤醒通道/看板编辑/看板服务/看板助理/量化总监/总监` 的 `kind/level/persona/slots` 全是空、`level` 一律默认 `member`。
   （`codex-套件` 自己是唯一的 Codex 侧真卡。）
3. 小瑕疵（不急）：`capability-manifest` 里 `secretStore` 是布尔，其余十项都是枚举 —— 风格不一致；**要改属契约改动，先报老板**（红线：契约先行）。

## 四、指导：下一步按这个顺序

1. **先提交 M0**（任务号 `KIT-001`）：建 `feature/kit-m0` 分支 → 提交 `core/ cli/ tests/ package.json docs/slug.md docs/reports/` → 推 `origin` 分支（**不自己合 main**，合入归 Codex 侧）。
   理由：留痕是红线，可移植的前提是"在版本库里"。
2. **KIT-002 已建卡**（落地脚本新建的），按它 §二做，但**先做这两个适配器**：
   - `outbound/board-append`：产出写回看板（带署名与引用）——主链路的出口；
   - `schedule/cron`：给"没有常驻"的 agent 定时唤醒——OPC 场景最需要的能力。
   其余四个（web-rpc-inject / watch-file / session-inject / watchdog）排后。
3. **补 Codex 侧卡（M1 的真活）**：给 `ack onboard` 加 `--draft`——从 `agents.json` + 工位路径推断 `kind`，自动生成草稿卡，人只填 `level/role`。
   这是"新员工一出现就自动入职"的落地方式，也是 App 员工页从空壳变真的唯一路径。
4. **守住回归**：每次改完跑 `npm test`（现在 34 条），不许掉绿；契约要动先报老板。

## 五、回滚点 / 证据

- 落地回滚点：`D:\agent_crew_kits\run\kit-handoff-backup\20260912-195345\`（org-levels.md.bak 等）
- 本次验收新增文件（`D:\agent_crew_kits`）：`agents\dsh-main.card.json`、`agents\dsh-quant.card.json`、`docs\tasks\KIT-002.md`、`docs\reports\REQ-KIT-DSH-001_roster.md`、`docs\org-levels.md`（追加 §六）
- 测试原始输出：`node --test` → `tests 34 / pass 34 / fail 0`
