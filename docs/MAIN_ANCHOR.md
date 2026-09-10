# 主线程锚点（2026-09-10 23:4x）

> 新主线程第一句：`读 docs/MAIN_ANCHOR.md + docs/ROLES.md，按 L1 主线程接管；先汇报当前局面与待办，不要通读历史。`

## 一、局面

- **git**：分支 `main`（9/10 04:2x 已立基线，311 项积压入库）；9/10 下午起的产出由 Codex 审阅后分批合入。**审阅+合入 main 由 Codex 负责**（老板 23:3x 授权，见 `DECISIONS.md` §3.10）。
- **交易/值守链**：常驻引擎与 `stockdb.exe` 在岗（心跳 `outputs/watch_heartbeat.txt`，盘后 `tasks=4`）；**禁止从任何 agent 沙箱 shell 启动引擎/托盘/stockdb**（9/10 的 10013 事故根因）。
- 9/10 事故：引擎被限网 → 账1/账2 **全天零成交**；15:45 用计划任务干净重拉；`QuantNetGuard` 在岗但 **alert-only、未武装**。
- 夜间链路已修复：20:15 扫描 / 20:40 计划曾双双静默失败（计划任务返回 1/2，引号 bug），已修复复核（候选 22:43、`next_plan` 22:44）。
- **DSH 唤醒已打通**：`POST /api/session/prompt` 可唤醒冷会话（21:43 实测 accepted + 0.9s 回复）；cookie 持久、跨重启有效；`launchToken` 从 `/home/lgy/.dsh-web.log` 取，**不需要老板手抄**。看板哨兵已能 `@dsh-老员工` 叫醒（19:40 干跑 PASS）；schedule overlay 降为备选。
- 会话工具：Hub `QuantCodexBoard`（Tailscale `100.64.75.72:8788`，`/api/ping` 200）；命名统一为**「前缀-对话框名」**（`docs/BOARD_NAMES.md`，`老板` 唯一例外），五处同名（标题/状态栏/@/署名/inbox 指派）。
- 平台约束：**代建线程会触发 DeepSeek 兼容 bug，新线程一律老板手动建**；跑在公共看板上的 `codex-*` 线各自有固定职责。

## 二、待办（见 docs/WORKBOARD.md）

1. AR-001 收尾：事件注入常驻触发器（挂计划任务上下文，**禁塞进 net_guard.py**）
2. RV-001 net_guard 两条 must-fix（抓不到旧 PID 必须中止；成功=旧 PID 全消失+新 PID 不同+心跳变新）→ 非交易时段受控武装实测 → 才谈常驻武装
3. RV-002 build_acct2 加固（**现只允许 `--dry`**）
4. 会话工具第三期：RPC 门铃 + 统一调度器；23:33 派发机制缺陷（`codex exec resume` 副作用）待整改
5. 待老板拍板：`docs/COMMS_BOARD.md` 是否进库（默认当运行态、不进库）；WebFetch 公网策略；dsh 版本锁定/交易时段禁升级

## 三、纪律

- 先 grep 后读；主线程只读一页报告；上下文 ~50% 就重锚换线程。
- 常驻引擎/托盘只能由计划任务或老板本人启动。
- 所有交付落文件；对话只是传输层。
