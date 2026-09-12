# HUB-008 审阅证据（承载层 + 公告重做 + 补投修复 + 未读口径）

- **提交人（署名）**：`codex-看板编辑 <codex-convtool@agents.canaanser.local>`
- **分支**：`feature/hub-carry-layer`
- **提交**：`193da69`（承载层 + 公告重做）→ `b9bbcb2`（补投修复）→ `51522df`（未读口径）
- **影响面**：`tools/mobile_chat/*`（Hub 服务端与手机页）+ `docs/*`；**未碰**别人的仓、未碰 `main`

## 一、交付物

| 件 | 说明 |
| --- | --- |
| 公告系统重做 | 每条公告有短号（`N-xxxx`）→ 回执写 `收到 N-xxxx` 或**引用回复**；裸词「收到」不算；发布即投各线信箱 + 尽力叫醒；超时催办（10 分钟一轮、最多 2 次） |
| 承载层接口 | `/api/meta`（能力协商·含派单候选）、`/api/employees`、`/api/items`（物料/节点时间轴）、`/api/ingest`（多来源归一）、`/api/read`、`/api/tasks`(+`/status`)、`/api/groups`、`/api/contacts`、`/api/events`(SSE) |
| 承接对接 | 退役条目灰显不消失、不代答/不投递；`@旧 slug` → 400 并指路；`refs.slug` 落板；`updateAgents()` 读前/写前 (mtime,size) 校验，冲突宁可 409 不覆盖 |
| 补投修复 | 见 §三 |
| 未读口径 | 见 §四 |
| 性能 | `/api/dialog` 220ms → 35ms（按 (mtime,size) 缓存解析 + 历史归档轮转） |

## 二、怎么验的（可复跑）

```powershell
# ① 端到端自测（隔离临时目录，不碰仓库运行态数据）
node tools/mobile_chat/selftest_v2.mjs          # → 201/201
# ② 真页面体检（390x844，无头浏览器）
node <vis>\make_ui_preview.mjs <vis>\ui_preview.html
E:\python\python.exe -B tools\mobile_chat\ui_check.py "file:///<vis>/ui_preview.html" 390 844   # → 54/54
```

> `selftest_v2` 现在支持 `--tmp <目录>`，**默认用项目内 `run/selftest-tmp`**（躲开 %TEMP% 的
> 8.3 短名，libuv `fs.watch` 会崩）；跑起来第一行会打印 node 版本 + 临时根，便于跨环境比对。

## 三、补投修复（`b9bbcb2`）—— 现场抓到的真 bug

**症状**：给某条线「退避到点后补投」**从未真正发生过**，日志里连一个字都没有。
**证据**：`state.json` 里那条线的账本是 `{done:true, nextAt:22:24:35}` —— 到点也不补投。
**根因**：`setWakeBook()` 是合并写，排 `nextAt` 的 5 个写点都没清上一轮遗留的 `done`，
而 `wakeRetryTick()` 第一句是 `if (b.done) continue` → 补投被**静默跳过**。
**修法**：① `done` 与 `nextAt` 互斥，只在 `setWakeBook` 这一个汇聚点归一（`nextAt>0` → 强制
`done=false`）；② 补投扫描只以 `nextAt` 为判据；③ 扫描里的 5 个静默分支全部留痕
（`WAKE RETRY DROP/STOP`）；④ `MCHAT_WAKE_RETRY_MS` 可配（默认 60000，自测 3000）。
**回归**：新增判别性用例（`done` 残留 + 已到点 → 必须仍被扫到，且账本必须收敛）。

## 四、未读口径（`51522df`，总监 2026-09-12 22:24 正式请求）

> **未读 = 该线信箱里 ts 比它「本人上一次发言」更新的行。**

- 排除 `〔代答〕`（程序顶着本线名发的，不算它说过话）；
- **退役档案条目（`<看板名>·退役`）不叫、不计**（实测原来虚报 7）；
- `/api/dialog`、`/api/contacts`、`/api/employees` **统一走同一个函数**（原来三处各写一遍）；
- 回归 5 条：旧留言算未读 / 发言后 N=0 / 真新留言 N=1 / **更晚的 `〔代答〕`不许吞掉新留言** / 退役=0。

## 五、未结 / 回滚点

- **未结**：线上需**重启看板**（计划任务）才生效；口径还没写进 `docs/DIALOG_HUB.md`。
- **回滚点**：分支上 `193da69` 之前即 `main@6d7f300`；Hub 在计划任务里，停/启各一条命令。
