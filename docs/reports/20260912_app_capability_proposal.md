# App 承载能力：把"套件"装进去需要什么（codex-总监 草案）

> 老板 2026-09-12 01:5x："App 至少要是简易版企业微信级别；卖点是配合套件做**无门槛项目管理**；
> 聊天、员工信息、项目物料、时间轴、归档、印章、项目周期；主页面先不涉及；
> agent 可以是服务器上的、也可以是个人电脑上的——**都当成不同来源，传同样的话**。"
>
> 本文只回答一件事：**App 要长出哪些"接入口 + 存储 + 展示"，才装得下套件。**（不含 UI 视觉设计）

## 0. 一句话

App 只需要做到**三通一板**：**人↔员工通**（消息）、**任务通**（单据）、**物料通**（指针），
外加**一块项目看板**；其余全是这三样的投影。

## 1. 愿望 → 六个数据面（现状体检是刚打线上接口，不是自报）

| # | 你的愿望 | 实体 | 真源（谁的账） | 现有接口 | 现状 |
| --- | --- | --- | --- | --- | --- |
| 1 | **员工**（状态/id/形象/权限/工位） | `AgentCard` | 套件 `agents/<slug>.card.json` + 本机 `.private/<slug>/state.json` | `GET /api/employees` ✅ | **9 条线只有 1 张真卡**（套件）；其余 `kind/level/persona/permissions/slots/capabilities` 全空、`level` 一律 `member` |
| 2 | **沟通**（多来源 agent） | `Message/Envelope` | `outputs/dialog/dialog.ndjson` + `pending_<slug>.ndjson` | `/api/post`·`/api/mail`·`/api/dialog`·`/api/events`(SSE)·`/api/contacts`·`/api/groups` ✅ | 能用；`/api/contacts` 9 条带状态/未读/头像 |
| 3 | **项目 / 任务 / 主线支线** | `Project` + `Task` | `docs/tasks/*.md` + `tasks_state.json` + `inbox/*.task.json` | `GET/POST /api/tasks`、`/api/tasks/status` ✅ | **67 条**（HUB 8 / 派单 13 / 转投 38；done 45）——但**没有 Project 实体**，现在的"项目"只是 ID 前缀 |
| 4 | **物料**（文档/截图/链接/产物） | `Material` | 无 | `GET /api/items` ✅ | **count = 0**，通道是空的、schema 没定 |
| 5 | **时间轴 / 归档** | `Timeline` | 各类 ndjson 合流 | 看板投影 | 消息有时间轴；任务/物料**没有汇进同一条时间轴** |
| 6 | **印章 / 审批**（你说后置） | `Seal / Receipt` | 套件 `spec/receipt.schema.json`·`spec/review.schema.json` | 无 | 先**留字段不做 UI**（进入下一阶段要有人盖章，这才是印章的真实用途） |

## 2. 六个设计决定（我的建议，含理由）

1. **App 与套件共用一套 schema**（直接把套件 `spec/*.json` 当契约）。
   理由：现在已经有分叉——`agents.json` 里 `level/role` 与套件卡不是一份账，谁改都容易"两边不一致"。
   做法：卡是**唯一身份真源**，App 只读卡 + 叠运行态（`lastSeen / pendingMail / currentTask / blockers`）。
2. **缺卡自动生草稿**：新线第一次发言 → App 建 `card.draft.json`（`kind` 由接入方式推断），人只填 `level/role`。
   这就是你要的"新员工一出现就自动入职"，而且不用人手抄。
3. **物料只存指针**：`{id, project, task, kind, title, path|url, hash, bytes, thumb, by, at}`，
   二进制留在工位，App 只存路径+哈希+缩略图。理由：我们自己的红线就是"真源在文件、投影可重画"。
4. **消息可挂载 `refs`**（task / material / record id）——讨论从此**挂得住**，不再散在聊天里。
   这是"聊天工具"升级成"项目沟通"的那一刀，也是跟企业微信真正的差别。
5. **"来源"抽象成 `transport`**：`queue | file | bridge | http`（本机 Codex、WSL dsh、远程机同构）。
   App 不关心对方跑在哪，只认「员工 + 信封」。这条直接沿用套件 `core/router` 的口径。
6. **一切 append-only，投影随时可重画**（现在已经这样，守住不要再引入"就地改历史"）。

## 3. 路标建议（每步都能独立验收）

| 里程碑 | 内容 | 验收 |
| --- | --- | --- |
| **M1 员工档案立起来** | 补齐 8 张卡（层级/职能/权限/插槽/形象）+ 把 `.private/<slug>/state.json` 接进 `/api/employees` + 单员工详情口 | 9 条线在 App 上**看得出身份、层级、在忙什么**；空席位灰显 |
| **M2 项目实体** | `projects.json`（负责人/成员/主线支线/周期 phase）+ 任务卡加 `project/parent/milestone` + `GET /api/projects` + 看板按项目切 | 任意任务能回答"属于哪个项目、上一级是谁、现在哪个阶段" |
| **M3 物料 + 时间轴** | `materials` schema + `POST/GET /api/materials` + 三类事件（消息/任务/物料）汇成一条时间轴 + 冷存归档 | 一个项目点开就是**按时间排的物料墙** |
| **M4 印章** | `seal`（谁、何时、对哪份东西、哈希）+ 阶段门 | 进下一阶段必须有章，没章走不动 |

## 4. 我加的五个想法（你说可以提，就往更好的方向提）

1. **员工卡加一个 `signature`（一句话签名）**：手机端气泡里一眼认人；配合现有头像（字+色相）成本几乎为零。
2. **空席位显式化**：没有会话的席位 = 职位挂在那里，App 上灰显、可被"招人"认领。
   现在 9 条线里 8 条是 `member`——那是**默认值不是事实**，M1 要修掉。
3. **隐藏代理**（你说的"精密设计部的代理"）：`level=system`，App 默认折叠，只在审计视图可见（可见性是个 filter，不是另一套数据）。
4. **项目周期门（gate）**：立项/开发/验收/交付/归档，每道门都要人**盖章**才放行——印章系统这么用才有价值，不是装饰。
5. **先拆 board.mjs 再谈承载**：它现在 **256KB 单文件**（页面+服务+API 挤一起），是"性能上限"的天花板。
   建议排在 M2 之前：只**搬家不改行为**（拆 `hub/` 服务与 `page/` 前端），回归用 183 自测 + 44 页面验收守着。

## 5. 线上体检原始数据（2026-09-12 01:5x）

```
GET /api/meta      → apiVersion=2, board.mjs/0.12, pageVersion=2026-09-10.48, transports=http+json,sse
GET /api/employees → count=9, kitDir=D:\agent_crew_kits, byLevel={member:8, lead:1}   ← 只有套件有真卡
GET /api/tasks     → count=67, byProject={HUB:8, 派单:13, 转投:38, ...}, byState={done:45, open:12, claimed:6}
GET /api/items     → count=0        ← 物料通道空
GET /api/contacts  → count=9（带 status/pendingMail/open/avatar/lastMsg）
GET /api/groups    → count=1（demo）
```

**结论：通讯层已经够用，员工层是空壳，项目/物料层还没开始。** 你要的"企业微信级 + 套件卖点"，
短板不在聊天，在**M1 员工档案**和 **M2 项目实体**这两块。

## 6. 需要老板拍板的三件

1. **员工卡的"唯一真源"放哪**：套件仓（`D:\agent_crew_kits\agents\`）还是 App 仓？我建议**套件仓**，App 只读。
2. **M1/M2 谁做**：套件线（codex-套件）做 M1（它本来就管员工/层级），看板编辑做 M2（接口在它手里）。我审。
3. **要不要先拆 board.mjs**：拆了更稳但会停一两个小时的功能开发；不拆就继续堆。
