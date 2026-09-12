# 最小运行模式（基线）· 2026-09-12 01:5x

> 老板："**先把现有的我们能承载的最小运行模式，保证它能运行。**一会儿再决定要不要去另开一条极限，
> 在那上面开发、在这上面验证。"
>
> 本文就是那条**基线**：它由什么组成、怎么验、坏了怎么回。

## 一、它由什么组成（最小集）

| 层 | 组成 | 位置 |
| --- | --- | --- |
| **常驻** | 计划任务 `QuantCodexBoard`（node 跑 `tools/mobile_chat/board.mjs`，端口 8788） | `Task Scheduler` |
| **辅工** | 计划任务 `QuantCrewHost`（每 5 分钟，`pythonw` 无窗口，镜像信箱到工位） | 同上 |
| **真源** | `outputs/dialog/dialog.ndjson`（通讯）、`docs/COMMS_BOARD.md`（看板投影）、`outputs/inbox/*.task.json`（派单）、`groups.json` / `halt.json` / `boss_events.ndjson` / `items.ndjson` / `tasks_state.json` / `read_state.json` | 仓库内 |
| **身份** | `outputs/dialog/agents.json`（名册）+ `docs/BOARD_NAMES.md`（名字真源）+ 套件员工卡 `D:\agent_crew_kits\agents\*.card.json` | 两仓 |
| **客户端** | 手机页 `http://100.64.75.72:8788/`（PAGE_VER `.48`） | — |
| **接口** | `api v2`：`/api/ping`·`/api/meta`·`/api/dialog`(带游标)·`/api/events`(SSE)·`/api/post`·`/api/send`·`/api/mail`·`/api/tasks`·`/api/groups`·`/api/contacts`·`/api/employees`·`/api/items`·`/api/ingest`·`/api/halt`·`/api/bind`·`/api/read` | 见 `DIALOG_HUB.md` §17–19 |

**一句话**：一个常驻服务 + 一组 append-only 文件 + 一个网页客户端 +（未来）任意个客户端通过 REST/SSE 接入。

## 二、怎么验（两条命令 + 一次体检）

```powershell
# ① 全量自测（隔离临时目录，不碰生产数据）—— 当前 183/183
node tools\mobile_chat\selftest_v2.mjs

# ② 真页面验收（无头 Chromium 真点击）—— 当前 44/44
node C:\Users\Administrator\.codex\visualizations\2026\09\10\01a08ab8-c2a7-7c02-943b-f217d2538a83\make_ui_preview.mjs ui_preview.html
E:\python\python.exe -B tools\mobile_chat\ui_check.py "file:///C:/Users/Administrator/.codex/visualizations/2026/09/10/01a08ab8-c2a7-7c02-943b-f217d2538a83/ui_preview.html" 390 844

# ③ 线上体检（不动数据）
GET /api/meta      → apiVersion/features   （客户端据此协商）
GET /api/employees → 员工（套件卡 + 运行态）
GET /api/dialog    → 通讯（37ms 级别）
```

## 三、基线版本（冻结参照）

| 项 | 值 |
| --- | --- |
| 页面版本 | `2026-09-10.48` |
| 接口版本 | `api v2`（`/api/meta` 自报） |
| 自测 | **183/183** |
| 真页面 | **44/44** |
| `/api/dialog` | mean ≈ **35ms**（优化前 220ms） |
| 重启方式 | `Stop-ScheduledTask QuantCodexBoard; Start-ScheduledTask QuantCodexBoard`（**要权限**；不自动持有） |

## 四、坏了怎么回（回滚点）

1. **代码**：`tools/mobile_chat/board.mjs` 之外的改动都在 `docs/` 与 `outputs/dialog/`（数据），
   代码回滚 = 恢复 `board.mjs` 上一个可用版本 → 重启；
2. **数据**：真源是 append-only，**没有"改坏"的路径**；投影（看板/页面）随时可重画；
   轮转归档在 `dialog.ndjson.archived`（只读不删）；
3. **名册**：`agents.json.bak`（每次迁移自动备份）+ `/api/bind` 换绑会记 `failedThreadIds`。

## 五、"另开一条极限线"的机制建议（**待老板拍板，先不做**）

老板设想：**另开一条线做激进开发，在这条基线上验证**。为不重演"两条线改同一个文件打架"（已发生过两次），建议：

1. **人**：由老板在 UI **手动新建**一个窗口（项目=量化交易软件、环境 local、标题如 `codex-看板极限`），
   我这边负责**登记**（`agents.json` + `BOARD_NAMES.md` + 信箱）——**不要用工具建线程**（会写坏）。
2. **代码**：极限线在自己的**功能分支**上开发；合入前由本线（基线线）跑 **183 自测 + 44 页面验收**。
3. **运行**：极限线用**独立实例**（不同端口 + 独立数据目录，如 `:8789` + `outputs/dialog-exp/`），
   避免两条线的 Hub 抢同一个 `dialog.ndjson`；
4. **数据**：实验数据**绝不写进基线目录**；稳定后再由基线线切回。
