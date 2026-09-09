# Agent 分工协议 (AGENT_SPLIT)

> 2026-09-10 老板拍板: **DSH(快)** 与 **Codex(稳/规范/学术)** 双 agent 协作, 防冲突。
> 双方(及老板)都照此执行; 有分歧老板仲裁。

## 1. 角色定位
- **DSH(本助手, 快)**: 值守/调度/模拟盘执行/每日计划/数据链路/回测快跑/即时修复/试错; 主 executor。
- **Codex(稳/规范/学术)**: 架构化重构/风控数学模型/回测框架严谨化/设计文档/高规范代码打磨/深度 review; **并负责调度治理(watch_bridge/唤醒/消息桥管理, 老板2026-09-10分配)**, DSH 不再自管桥。
- 老板: 唯一验收人, 仲裁。

## 2. 真源与所有权(同一时间仅一方可改, 改前登记)
| 文件/目录 | 性质 | 改动前登记 |
|---|---|---|
| core/risk/sellrules.py | 卖出规则唯一真源 | 必须登记+对方review |
| core/trade/ledger.py | 台账唯一真源 | 必须登记 |
| core/trade/file_order_broker.py | 下单/回报真源 | 必须登记 |
| core/lib/*(orderfile/rdx/quotes/emq_arch/dbfread) | 公共库 | 登记+测试 |
| duty/duty_engine.py, duty/schedule.yaml | 值守引擎 | 登记+dryexec验证 |
| self_api.py(根) | 对外冻结接口 | 接口冻结, 改动须老板批 |
| scripts/(gen/compose/watch_bridge/close_check/…) | 业务脚本 | 用前读注释, 改后干跑 |
| docs/*, DECISIONS.md | 规则/结论 | 追加, 不覆盖结论 |

## 3. 交接与消息桥
- 目录: `outputs/inbox/` — 投递新任务; `outputs/inbox/done/` — 已完成归档; `outputs/inbox/reports/` — 回报。
- 投任务(任一方→另一方): 写 `inbox/<时间戳>_<from>.task.json`:
  ```json
  {"to":"dsh|codex","do":"改什么/查什么","target":"文件或范围",
   "why":"原因/背景","accept":"验收标准(回测/dry/规范)"}
  ```
- 收到方: 读任务 → 执行 → 移到 `inbox/done/` → 在 `inbox/reports/` 写 `<时间戳>_<who>.report.md`(改了哪些/结果/如何验证)。
- DSH 侧: `watch_bridge` 每 30s 检查 inbox 有未处理 task 即唤醒 DSH 处理(对 Codex 投的自动接活)。

## 4. 冲突铁律
1. 单一真源同一时间仅一方改(见§2登记);
2. 涉及下单/资金/策略参数任何改动: 先回测或 dryexec, 老板点头才上线(模拟盘也守此纪律);
3. Codex 改动 → DSH 做回测/dry 验证; DSH 改动 → 交 Codex 看规范(可后补);
4. 各自工作日志写进 docs/dev_notes(按日), 双线账户(组合 a0de4b75 / 做T 5e3d)分开记录。

## 5. 当前活跃(2026-09-10)
- DSH 主责: 9/10 14:44 组合执行观察/复盘; 账户2建仓(待开盘); 做T离线研究; 双线日报。
- Codex 候选活: 规范 review 值守引擎/计划器; 做T规则学术化(滑点/回补纪律/回测严谨化); MCP/管理链设计。
- 老板待定: 账户2扫单目录确认(C:\emq\日内分钟), 管理智能体/Codex 分工后推进。

## 6. Git 工作流(老板 2026-09-10 更新, 取代此前"git 一律不动"口径)
- `main` 写保护: 任何合入 `main` 前必须 Codex 主审阅通过 + 老板同意; DSH 不得自行合 `main`。
- 实验/功能分支(feature/* 等): DSH/Codex 可自由创建、提交、推送; 分支上提交无需审批。
- 合 main 前的审阅由 Codex 负责(规范/架构/风控/验收); 下单/资金/策略参数改动须先回测或 dryexec。
- 当前 HEAD `842a7bd`, 工作分支 `feature/risk-consolidation`(311 项积压); 积压与清理细节见 `GIT_GAP_20260910.md` / `FILE_INVENTORY.md`。
