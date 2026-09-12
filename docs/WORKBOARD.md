# 任务台账（主线程维护）

| 任务ID | 标题 | 执行角色 | 负责人/线程 | 状态 | 交付物 |
|---|---|---|---|---|---|
| CT-001 | 会话工具 v2 第一期（全渠道入 Hub + 接单锁） | 工具开发 | “看板编辑”线程 | 进行中 | `tools/mobile_chat/*`、`docs/CONVTOOL_V2_PROGRESS.md` |
| CT-002 | 手机页第二期（筛选/未读/引用/搜索） | 工具开发 | 待开 | 未开始 | `tools/mobile_chat/board.mjs` |
| RV-001 | net_guard 是否武装自动重启（复审收口） | 审阅 | 待开 | 未开始 | `docs/reports/RV-001_review.md` |
| RV-002 | build_acct2 P2 加固（防重/整手/涨停/差额） | 审阅+开发 | 待开 | 未开始 | `docs/reports/RV-002_review.md` |
| AR-001 | DSH 唤醒通道攻坚（RPC 门铃 + 保持清醒链条） | 架构 | 新线程（手动建） | 待接手 | `docs/tasks/AR-001.md`、`docs/reports/AR-001_arch.md` |
| OP-001 | dsh 实例署名落地（DSH-main / DSH-quant 声明） | 运维 | 老板+dsh | 未开始 | 看板实例面板变绿 |
| CT-003 | 长按 @ 提及并入第二期（主线程误做，移交复核+补测试） | 工具开发 | “看板编辑”线程 | 待接手 | `docs/tasks/CT-003.md`、`CONVTOOL_V2_PROGRESS.md` |

> 归属规则：产品（如会话工具 Hub）由“工具开发”角色拥有，**不绑定具体线程**；每期开新线程，交接靠 `docs/CONVTOOL_V2_ANCHOR.md` + 进度文档 + 一页验收报告。主线程不参与产品实现细节，只发任务卡、读报告、更新本台账。
