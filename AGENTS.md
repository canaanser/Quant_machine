# AGENTS.md — Quant_Alpha_System 双 Agent 协作与工作纪律

> 本文件供 Codex 会话自动加载；dsh 侧对应 `docs/AGENT_SPLIT.md` 与 `docs/TO_CODEX_BRIDGE.md`。

## 角色
- Codex（本 agent）：**主审阅** / 架构 / 规范 / 风控数学 / 回测严谨化；负责调度治理（watch_bridge / 唤醒 / 消息桥）；**并负责代码审阅与合入 `main`**（老板 2026-09-10 授权）。
- dsh：主执行（双线执行/研究/盯盘/复盘/写代码快）；不自行合主分支、不管桥与调度。
- 老板：唯一仲裁；主分支合并的最终拍板人。

## 开工必读（按需定位，禁止全文考古）
- `docs/STATE_ANCHOR.md`（运行现状）
- `docs/AGENT_SPLIT.md`（真源与互审）
- `docs/TO_CODEX_BRIDGE.md`（桥与调度交接）
- `docs/DATA_ARCH_FOR_CODEX.md`（数据服务与坑位）
- `docs/FILE_INVENTORY.md`（目录底图：在用/待机/可清）
- `docs/GIT_GAP_20260910.md`（积压差异）
- `DECISIONS.md` §3.8/§3.9 + `docs/dev_notes/` 最新日报尾部待办

## 成本纪律（老板定）
- 先 grep 定位，命中再看小段；禁止一上来整文件 read/cat。
- 输出看摘要；大结果落盘；同一内容不重复读第二遍。
- 每轮自省是否真的需要新工具调用；没事不开轮。

## Git 工作流（老板 2026-09-10 更新）
- `main`：合入由 **Codex 负责**（老板 2026-09-10 授权）：Codex 主审阅通过即可合入，不再逐次等老板点头。dsh 仍不得自行合 `main`。
- 实验/功能分支（`feature/*` 等）：可自由创建、提交、推送；分支上的提交不需要审批。
- 合入 `main` 前的审阅由 Codex 负责（规范/架构/风控/验收）；**涉及下单、资金、策略参数的改动必须先回测或 dryexec 验证**，这条不因授权而放宽；审阅结论落 `docs/reports/<id>_review.md`。
- 当前：分支 `main`，HEAD `4ef3d7c`（9/10 04:2x 已把 311 项积压作为「主分支基线」提交，`docs/GIT_GAP_20260910.md` 已过期）；9/10 下午起的改动由 Codex 分批审阅后合入。

## 红线
- 不重复拉起值守引擎（`duty/duty_engine.py`）与 `stockdb.exe`。
- 数据更新.exe 不自退：必须按 `scripts/run_data_sync.py` 流程“启动 → 到点关闭 → 定稿”。
- 单文件/真源改动按 `AGENT_SPLIT.md` §2 先登记；文件“废弃不删只标记”；删除候选见 `FILE_INVENTORY.md`。
- 跨 agent 任务走 `outputs/inbox/`：投 `*.task.json` → 完成后移 `done/` → 回报写 `reports/`。
