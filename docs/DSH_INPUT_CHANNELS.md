# DSH 自身输入/唤醒通道清单(2026-09-10 实测)

> 目的:老板要把"只能靠他说话"扩成"事件/时间驱动"。本文是**实测结论**(每条带证据),不含推测。
> 实测人:DSH(GUI 会话 `session-4258a4fe-4dbd-49f7-a12b-67a5fa153417`),实测时间 2026-09-10 16:0x–16:2x。

## 一、能开启/延续 DSH 回合的通道

| # | 通道 | 机制 | 现状 |
|---|---|---|---|
| 1 | 这个 GUI 聊天框 | 老板输入 → 开新回合 | **唯一在用** |
| 2 | **goal 自动续轮** | `create_goal` 建目标后平台自动继续本会话(可设 `max_goal_rounds`;三回合判定 blocked) | 今天就能用;现被我设 `blocked` 以防空转烧 token。**"它能自己醒"最可能是这条** |
| 3 | 同会话内部 | `subagent` / `workflow` / `jobs` / `ralph` | 只在回合内并行,不能跨回合唤醒 |
| 4 | **`@deepseek-ai/dsh-schedule`** | agent 自设**延时/绝对时刻/固定间隔(≥5 分钟)**提醒;到点**以同会话 follow-up 消息**叫醒;持久(重启仍在);live+idle 立即投递;cold 会话保持逾期直到被恢复 | **已安装、从未启用**(证据:web profile 的 `cordis.patch.yml` 为空,`.bak`/`.disabled` 仅注释)。启用需**会话开始前**加载 overlay |
| 5 | **Web RPC 直达活会话** | `POST /api/remote.mux`,命名空间 `session` 方法:`create / resume / prompt / follow / list / cancel` | 凭据缺口。实测:loopback 通过 Host/Origin 信任栅栏(否则 403),缺签名 cookie → **401**;cookie 由 `dsh web` 启动时终端打印的 **`?token=`** 换取,天级持久 |
| 6 | `@deepseek-ai/dsh-webhook`(+`-github`) | 外部事件 → **新建**根会话(workspace/title/prompt/preset/权限) | 装了未启用;新会话,无本会话上下文 |
| 7 | `@deepseek-ai/dsh-hooks-codex` | 复用 Codex `hooks.json` 五个 hook 点(会话开始/提示词提交/工具前后/将停止):可附加上下文、阻塞、**强制继续** | 装了未启用;能续不能启 |
| 8 | `@deepseek-ai/dsh-acp` | 标准 ACP(JSON-RPC stdio)服务器:create/resume/prompt/cancel/挂 MCP | 装了未启用 |
| 9 | CLI | `dsh --profile headless "<任务>"`(一次性新会话)、`dsh --profile tui --resume <会话>` | **Codex 的桥现在用的就是 headless**(today 15:58 派单) |

## 二、明确无效(别再试)
- Windows 计划任务:只能起进程,**不能**给 GUI 会话投消息。
- 看板 `docs/COMMS_BOARD.md` 的 `@dsh` 留言 / `outputs/inbox/*.task.json`:只是文件。今天 Codex 的 relay 投了 12 条,一条都没叫醒我。
- 往 `~/.dsh/sessions/**/session.jsonl.zstd` 追加内容:日志由活着的服务端独占持有,不是受支持通道。

## 三、关键证据(可复核)
- 端口:`ss -ltnp` → `127.0.0.1:3080` 由 pid 3747(`dsh web`)监听。
- 认证:`dsh-client-connection` 实现里 `TOKEN_QUERY = "token"`、`COOKIE_PREFIX = "dsh-auth-"`、"只有带 token 的根请求铸造 cookie 并重定向到干净 `/`;有效 cookie 才发 index;其余一律最小 401";`requestRejection()` = 不受信 → 403,未认证 → 401。
- 提示:curl 探测必须先绕开环境代理(`--noproxy '*'`),否则会被挂掉的 `http_proxy=127.0.0.1:7890` 劫持成连接失败(今天差点误判成"端口不通")。
- RPC 方法:`@deepseek-ai/dsh-api-session-controller` 的 `super(ctx,"sessionController",{namespace:"session"})` 与 `prompt/resume/create/follow/cancel` 方法名。
- schedule 未启用:web profile `package.json` 的 bundles = `dsh-base` / `dsh-web-app` / `deepseek-web-import` / `dsh-roundify`;`cordis.patch.yml` 空。

## 四、建议的两步(待老板点头,未执行)
1. **按时间醒**:启用 schedule overlay → 我给自己排守盘时刻表(09:20 盘前双线检查 / 10:30 中盘 / 13:05 / 14:35 尾盘前取价自检 / 15:05 收盘核对 / 20:45 计划复核)。
   待用 patch 内容(写在 `~/.dsh/profiles/web/cordis.patch.yml`,**尚未写入**):
   ```yaml
   - insert:
       - id: schedule
         name: '@deepseek-ai/dsh-schedule'
       - id: schedule-ui
         name: '@deepseek-ai/dsh-client-ui-schedule'
   ```
   代价:重启一次 `dsh web`;提醒工具只给**overlay 加载后新建**的会话,所以重启后**新开一个会话**并首句贴 `docs/STATE_ANCHOR.md` 接续。
2. **按事件醒**:老板把 `dsh web` 终端里带 `?token=` 的启动 URL 给我 → 我换持久 cookie 交给外部守护(`scripts/net_guard.py` 或 Codex 的桥),在"引擎掉线/数据同步完/14:44 执行结果"等事件发生时直接 `session.prompt` 叫醒我。
   代价:官方 RPC 但无面向自动化的文档;token 每次重启轮换,cookie 长期有效。

两步叠加后,日常守盘可不依赖老板在场;需要他判断的决策(建仓/加减仓/规则改动)才叫他。

---

## 六、0.1.5-rc.1 复核（Codex，2026-09-10 16:5x）

> dsh 已升到 `@deepseek-ai/dsh@0.1.5-rc.1`（web profile bundles 未变，`cordis.patch.yml` 仍为空）。

- **schedule 通道仍在**：`@deepseek-ai/dsh-schedule` 与 `@deepseek-ai/dsh-client-ui-schedule` 均为 0.1.5-rc.1。
  官方 README 说明：提醒以“同会话普通 follow-up 消息”投递；**投递需要活着的 root agent**，会话关闭则提醒保持逾期直到恢复；间隔最小 5 分钟；无 push/email/短信。启用方式：给 web profile 加 overlay（`cordis.patch.yml`，内容见本文件第四节），重启 `dsh web`，并在重启后新开会话接续。
- **Web RPC 入口仍在**：`POST http://127.0.0.1:3080/api/remote.mux` 实测返回 `401 unauthorized`（无凭据即拒），说明端点存在且鉴权仍是签名 cookie；与第一节第 5 条的结论一致。
  token 来源未变：`dsh web` 启动终端打印的 `?token=`（当前实例在 pts/0 交互终端里，无法程序化读取）；如需自动化，需老板提供该 URL，或把 `dsh web` 用带日志重定向的方式重启以捕获 token（token 每次重启轮换）。
- **桥在新版本下兼容**：实测派单冒烟通过（4 秒返回“桥已验证”）。新版 headless 把进度流写入 stderr、最终结果写入 stdout，正好与桥的取值方式一致。
- **新增进度流**：桥已打补丁（见 `docs/BRIDGE_NOTES_DSH.md`），把 headless 的 stderr 按 2 秒缓冲合并成可读进度，写入 `outputs/dialog/dsh_progress.ndjson`，由 Hub 转成 `kind="progress"` 记录（只展示、不路由、不当作提问）。

---

## 七、Web RPC 门铃：已打通（Codex 实测，2026-09-10 18:1x–18:2x）

> 结论：**RPC 门铃打通**。`session/list` → `session/create` → `session/prompt` 端到端实测成功，全程不需要 GUI 点击，也不需要 WSL 交互终端。
> 本节同时更正第一节第 5 条的一处误记。

- **更正：真实 RPC 端点不是 `/api/remote.mux`。** 那是 Typert Remote 的 **WebSocket 流**路由（源码 `REMOTE_STREAM_MUX_PATH`）。HTTP RPC 端点是 **`POST /api/<namespace>/<method>`**（例：`POST /api/session/list`）。带有效 cookie 对 `/api/remote.mux` 发 POST，实测 **404 not found**。
- **信封**：`{"type":"client-request","rpcId":"<uuid>","method":"<namespace>/<method>","payload":{"args":{…}}}`。`method` 必须与 URL 里的端点串逐字相同，否则回 `gateway/bad-request`。
- **`args` 是「参数名 → 值」映射**，参数名取自服务端方法签名：`session.list(_request, signal)` → `{"_request":{}}`；`session.prompt(request, signal)` → `{"request":{…}}`。多写/漏写字段都会 `gateway/arguments-invalid`（错误信息会直接点名缺哪个字段）。
- **`session.prompt` 必填字段**：`sessionId` / `requestId` / `mode`(`"queue"`|`"steer"`) / `content`（`[{ "type":"text","text":"…" }]`）。缺 `mode` 会在 wire 边界校验就失败。`requestId` 是去重键：同一 id 重复投递只入队一次。
- **换 cookie 的正确姿势**：`GET /?token=<launchToken>`（Host 必须是 `127.0.0.1:3080`），成功返回 **303 + Set-Cookie**，之后请求带该 cookie 即过鉴权。cookie 名 = `dsh-auth-<base64url(sha256(Host))>`，**与 Host 绑定**，换 host/port 就是另一个 cookie 名。
- **401 与 403 的分界**：`requestRejection()` 先过 Host/Origin 信任栅栏（不受信 → **403**），再校验 cookie（缺失/失效 → **401**）。之前「`?token=` 换完 cookie 仍 401」的根因是**用了重启前轮换掉的旧 token**——token 每次重启轮换，cookie 才持久。
- **cookie 跨重启有效**：签名密钥持久化在 `~/.dsh/.credentials.yaml` 的 `client-connection/browser-session` 记录里（该文件 mtime 早于 17:23 那次 `dsh web` 重启），校验只比对 `authority` 与签发/过期时间。此项为**代码+文件证据**，未做真实重启复测（重启会打断老板在用会话）。
- **token 抓取**：`/home/lgy/.dsh-web.log`（`dsh web` 以 `> 日志 2>&1 &` 方式启动即可程序化读取）。
- **凭证纪律**：token 只从日志读、cookie 只落 `chmod 600` 的仓库外文件；探测脚本不打印任何 token/cookie 值。
- **冷会话可被直接唤醒（已实测）**：`session/prompt` → `resolveAgent` → `resolve()`（源码注释 "Resolve or resume one ordinary Session"）。实测对一个最后活动在 04:39、早于 17:23 `dsh web` 重启的空白会话投 prompt，`accepted=true` 且 0.9 s 产出回复。**推论：时间驱动不需要用 5 分钟保温链，系统定时器到点直接点名即可**；保温链只在凭据不可用时当兜底。
- **同 requestId 去重有竞态窗口**：同一 `requestId` 同毫秒连投 2 次会**开出 2 个回合**；间隔 6 s 再投则只开 1 个。触发器重试必须拉开间隔（建议 ≥5 s）并自持状态。
