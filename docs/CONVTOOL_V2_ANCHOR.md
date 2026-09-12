# 会话工具 v2 建设锚点（2026-09-10）

> 给新 Codex 线程的第一份上下文。读完本文件 + `docs/DIALOG_HUB.md` 即可接手。

## 一、目标

把老板 / Codex / DSH 三方沟通的“会话工具”建成**常驻、可路由、可审计**的统一对话层：
标准记录 + 多实例身份 + 跨端适配（手机页 / 看板文件 / inbox / 桥）。

## 二、现状（已上线）

- **服务**：`tools/mobile_chat/board.mjs`（Node），计划任务 `QuantCodexBoard`（开机自启、失败重试、监听重试），地址 `http://100.64.75.72:8788`（Tailscale 私有）。
- **访问**：`http://100.64.75.72:8788/?t=<token>`；token 在 `C:\Users\Administrator\.codex\mobile_chat\token.txt`。
- **数据**（均运行态、不进 git）：
  - `outputs/dialog/dialog.ndjson`：标准记录 dialog.v1（id/ts/from/to/channel/kind/body/refs/state）。
  - `outputs/dialog/dsh_progress.ndjson`：dsh headless 进度流（2 秒缓冲，单条≤300 字）。
  - `outputs/dialog/agents.json`：实例注册表（primary=dsh-main；dsh-main / dsh-quant / codex）。
- **看板文件**：`docs/COMMS_BOARD.md` 仍是人类可读渲染 + dsh 侧读写入点；Hub 双向同步（进：新行归一；出：appendBoardLine）。
- **桥（WSL `~/.dsh-bridge`）**：MCP 服务 + `dsh-codex-mail`；已打进度补丁（stderr→`dsh_progress.ndjson`），备份 `server.mjs.bak-progress-20260910`，补丁脚本 `tools/mobile_chat/patch_bridge_progress*.mjs`。
- **dsh 侧**：`@deepseek-ai/dsh@0.1.5-rc.1`；web profile 已启用 schedule overlay（`cordis.patch.yml` + `tools/mobile_chat/schedule_overlay.mjs apply|revert`）；主会话（cwd `/home/lgy/lab/股票`）已建 5 分钟测试提醒（17:31 准点触发，时间唤醒通道验证通过）+ 6 条守盘提醒。`dsh web` 由 `setsid nohup` 启动，日志 `/home/lgy/.dsh-web.log`，token 每次重启轮换。
- **时间轴派单**：board.mjs 内置 watch_bridge 事件（09:20/10:00/10:30/11:15/11:30/13:10/14:00/14:30/14:44/15:08）+ 心跳>150s 应急，投 `wake_dsh_*` 任务到 `outputs/inbox`。
- **身份路由**：`@dsh` → primary（dsh-main）；`@dsh-xxx` → 指定实例；任务文件 `board_<alias>_<ts>.task.json`，含 `instance`/`claimedBy`。
- **手机页**：标准记录渲染（对话气泡 + 进度细行严格区分）+ 顶部实例面板（在线/待办数）。

## 三、待办（按蓝图）

**第一期剩余（优先）**

1. **全渠道入 Hub**：把 `outputs/inbox/*.task.json`（含 `done/`）与桥信箱 `~/.dsh-codex-bridge`（WSL，可用 `wsl.exe` 或 `\\wsl.localhost`）的消息归一成 dialog 记录（channel=inbox/bridge，kind=task/report）。
2. **接单锁**：派单时写 `claimedBy=alias`、`state=dispatched`；实例回复后自动标 `done`；超时未回在页面显示“待办”。

**第二期**：手机页筛选（按实例/未读）、引用回复、搜索、状态徽标、通知。

**第三期**：RPC 门铃（`POST /api/remote.mux`，token→cookie 目前 401，需继续攻；网页自身就是走这个 RPC）+ 统一调度器（时间轴/事件/心跳一套）。

**第四期**：权限与审计（各实例能干什么、成本账；`tools/mobile_chat/cost_report.py` 已有按会话统计）。

## 四、纪律（务必遵守）

- git 一律不动；改动只落工作区。
- 常驻引擎/托盘**只能由计划任务或老板本人启动**，禁止在任何 agent 的沙箱 shell 里拉起（2026-09-10 的 10013 事故根因）。
- 不重复拉起 `duty_engine`/`stockdb`；数据更新走 `scripts/run_data_sync.py` 流程。
- 成本：先 grep 定位再看小段，不整读大文件；`kind=progress` 的记录只展示，不路由、不回复、不派单。
- 每次改动必须：`node --check` → 重启 `QuantCodexBoard` → 用 token 调 `/api/ping`、`/api/dialog` 自测 → 结果写 `docs/CONVTOOL_V2_PROGRESS.md`。

## 五、关键路径速查

**开工第一件事**：读自己的看板信箱 `outputs/dialog/pending_codex-convtool.ndjson`
（别人/老板看板 @ 这条线时，服务投不进来就会把原话落在这里；不看等于漏消息）。

- 服务代码：`tools/mobile_chat/board.mjs`；测试/工具：`tools/mobile_chat/*.mjs`、`cost_report.py`。
- 计划任务：`QuantCodexBoard`（会话服务）、`QuantNetGuard`（引擎安全网，alert-only）、`QuantTrayOnLogon`（值守）。
- 对话数据：`outputs/dialog/`；token/状态：`C:\Users\Administrator\.codex\mobile_chat\`。
- 桥：WSL `~/.dsh-bridge`、信箱 `~/.dsh-codex-bridge`。
- 文档：`docs/DIALOG_HUB.md`、`docs/BRIDGE_NOTES_DSH.md`、`docs/DSH_INPUT_CHANNELS.md`、`docs/HANDOVER_20260910.md`。

## 六、新线程第一句（可直接复制）

继续建设“会话工具 v2”。先读 `docs/CONVTOOL_V2_ANCHOR.md` 与 `docs/DIALOG_HUB.md`，确认现状后，做第一期剩余两项：①全渠道入 Hub（inbox 任务 + 桥信箱归一）；②接单锁（claimedBy，未回=待办，回复自动消）。只改 `tools/mobile_chat/*`，不动 git；改完 `node --check` + 重启 `QuantCodexBoard` + 自测并写 `docs/CONVTOOL_V2_PROGRESS.md`；然后按蓝图进入第二期。

## 七、本线程的权限与边界（Codex 主线程分配，2026-09-10）

**看板身份**：`codex-convtool`（已在 `outputs/dialog/agents.json` 注册）。回报格式：`- @老板 时间 codex-convtool：内容`。

**允许**

- 编辑 `tools/mobile_chat/` 下的服务与工具脚本；编辑 `docs/CONVTOOL_V2_PROGRESS.md` 等进度/说明文档。
- 运行只读检索（rg/grep）、`node --check`、`node <脚本>`；用 token 调 `/api/ping`、`/api/dialog`。
- 通过 `wsl.exe` 读取 `~/.dsh-bridge`（确需修改时先备份，并在进度文档里登记）。
- 重启计划任务 `QuantCodexBoard`（`Start-ScheduledTask -TaskName QuantCodexBoard`）。

**禁止**

- git 任何写操作：不提交、不切分支、不合并。
- 从任何 agent 沙箱 shell 启动/重启值守引擎、托盘、`stockdb.exe`、数据更新（2026-09-10 事故根因）。
- 修改 `duty/`、`core/`、`scripts/` 下的交易逻辑；确需改动先出方案，交主线程/老板拍板。
- 读取或外传任何密钥；token 只在本机使用，不写进文档、不进仓库。

**沟通**

- 与主线程/其他任务的直接消息受平台“委派包装”兼容问题影响（DeepSeek provider 报 `missing field call_id`），不可靠；跨线程沟通优先走共享看板与 `outputs/inbox`。
