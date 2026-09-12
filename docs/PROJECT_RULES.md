# PROJECT_RULES — 量化交易软件（Quant_Alpha_System）项目专属规矩

> 🔖 **按级别读**：先跑 `node tools/mobile_chat/whoami.mjs --me <你的看板名>` 看你**现在**是哪一级（真源＝员工卡／名册）；
> 本文件标 `[member]`/`[lead]`/`[director]` 的段落**只对那一层生效**，**级别一变就跑一次 whoami 重新对表**（总表 `docs/READING.md`）。

> **通用规矩在 `AGENTS.md`**（所有线、所有项目都读那份）；**本文件只写这个项目专属的东西**。
> 换项目 = 换这份文件，`AGENTS.md` 不动。

## 一、本项目的角色分工（细节）

- **Codex（本侧）**：主审阅 / 架构 / 规范 / **风控数学 / 回测严谨化**；负责调度治理（watch_bridge / 唤醒 / 消息桥）；**负责代码审阅与合入 `main`**（老板 2026-09-10 授权）。
- **dsh**：主执行（双线执行 / 研究 / 盯盘 / 复盘 / 写代码快）；不自行合主分支、不管桥与调度。
- 老板：唯一仲裁；主分支合并的最终拍板人。

## 二、本项目开工必读（按需定位，禁止全文考古）

- 看板信箱：`outputs/dialog/pending_<slug>.ndjson`；自己那条线**开工先读自己的信箱**。
- `docs/STATE_ANCHOR.md`（运行现状）
- `docs/AGENT_SPLIT.md`（真源与互审）
- `docs/TO_CODEX_BRIDGE.md`（桥与调度交接）
- `docs/DATA_ARCH_FOR_CODEX.md`（数据服务与坑位）
- `docs/FILE_INVENTORY.md`（目录底图：在用/待机/可清）
- `DECISIONS.md` §3.8/§3.9 + `docs/dev_notes/` 最新日报尾部待办

## 三、本项目红线（工程侧）

- **不重复拉起值守引擎**（`duty/duty_engine.py`）与 `stockdb.exe`。
- **数据更新.exe 不自退**：必须按 `scripts/run_data_sync.py` 流程"启动 → 到点关闭 → 定稿"。
- **单文件/真源改动**按 `docs/AGENT_SPLIT.md` §2 先登记；文件"废弃不删只标记"；删除候选见 `docs/FILE_INVENTORY.md`。
- **跨 agent 任务**走 `outputs/inbox/`：投 `*.task.json` → 完成后移 `done/` → 回报写 `reports/`。

## 四、本项目交付纪律（钱与盘口相关）

- **涉及下单、资金、策略参数的改动**：必须先回测或 `dryexec` 验证，**这条不因任何授权放宽**；审阅结论落 `docs/reports/<id>_review.md`。
- 组合账与做T账**分开记录**（组合 a0de4b75 / 做T 5e3d）。

## 五、本项目的文档索引（这些是项目资产，不是公司规约）

| 文件 | 用途 |
| --- | --- |
| `docs/AGENT_SPLIT.md` | 真源与互审、谁改哪个文件要先登记 |
| `docs/BOARD_NAMES.md` | 看板名册（名字真源） |
| `docs/RUNBOOK_LOOP.md` | 开发→验收→开发 闭环契约 |
| `docs/RUNBOOK_SUCCESSION.md` | 承接（换人）流程 |
| `docs/PROJECT_RULES.md` | **本文件**：项目专属规矩 |
