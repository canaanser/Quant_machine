# 可移植架构：项目工程通讯软件（承载层）· v1 · 2026-09-12

> 本文是把**现在这套东西**抽成"可以搬到别的项目去跑"的架构说明。
> 对照物：套件侧的 `D:\agent_crew_kits\docs\architecture.md`（那边是**员工工厂**，这边是**承载层**）。
> 一句话：**套件负责把 agent 变成"员工"，这一层负责让这些员工像一支团队一样沟通、派活、留痕。**

---

## 一、定位与边界（先划清，否则一定做重）

```
┌──────────────────────────────────────────────────────────────────────┐
│  人（老板 / 项目经理 / 组长）                                          │
│      ↑  网页 / 未来 App                      ↓ 拍板、验收               │
├──────────────────────────────────────────────────────────────────────┤
│  承载层（本仓 tools/mobile_chat/，本文主角）                            │
│    · 通讯：记录 / 信箱 / 看板 / 群组 / 已读                              │
│    · 工程：任务卡 / 派单 / 状态 / 物料·节点（时间轴）/ 项目分组           │
│    · 治理：暂停闸 / 系统播报 / 署名审计 / 可见化规矩                      │
│    · 客户端：网页（第一个客户端）；未来 App（第二个客户端）                │
├──────────────────────────────────────────────────────────────────────┤
│  适配层（本层内部，但**唯一允许碰平台**的地方）                           │
│    · 入：看板行 / inbox 任务 / 桥信箱 / 任意来源（/api/ingest）           │
│    · 出：codex queue（秒级唤醒）→ exec resume（备选）→ 信箱（兜底）        │
├──────────────────────────────────────────────────────────────────────┤
│  员工工厂（套件 D:\agent_crew_kits，**真源在那边**）                     │
│    · 员工卡（身份/等级/权限/插槽/能力）· 运行态 state.json · 生命周期     │
└──────────────────────────────────────────────────────────────────────┘
```

**边界三条**：

1. **员工真源在套件**（`agents/*.card.json` + `.private/*/state.json`）；承载层**只读不写**，只做投影。
2. **通讯真源在承载层**（append-only NDJSON）；页/看板/状态栏都只是**投影**，可随时重画。
3. **平台差异只在适配层**：换平台 = 加/换适配器，内核与协议一行不改。

---

## 二、不变量（照抄套件的 I1–I5，再加承载层自己的 P1–P6）

| # | 不变量 | 在本层体现 |
| --- | --- | --- |
| I1 | 真源唯一，append-only，投影可重建 | `dialog.ndjson` / `items.ndjson` / `boss_events.ndjson` 只追加；看板 md、页面、群组视图都是投影 |
| I2 | 可寻址：`id/ts/from/to/kind/body`，`to` 能解析到**已注册名** | 每条记录都有；未注册会被拒或归一 |
| I3 | 投递与唤醒分离 | 协议只保证"送达"；醒不醒由适配器（queue/resume）+ 值守兜底 |
| I4 | 命名唯一：`前缀-短名`，五处一致 | `docs/BOARD_NAMES.md` 是真源；`agents.json` 是投影 |
| I5 | 交付落文件 | 对话是传输层；产物必须落盘（`docs/`、`outputs/`、物料 `path/url`） |
| **P1** | **零第三方依赖** | 只用 Node 标准库（无 npm 依赖、无构建步骤）→ 搬哪儿都能跑 |
| **P2** | **一条命令能起，一条命令能停** | `node tools/mobile_chat/board.mjs`；常驻交给计划任务 |
| **P3** | **一切路径/端口/身份走 env** | `MCHAT_WORKSPACE / MCHAT_DATA / MCHAT_MAILBOX_DIR / MCHAT_TASKS_DIR / MCHAT_KIT_DIR / MCHAT_THREAD_LOCKS / MCHAT_CODEX_BIN / BOARD_PORT / MCHAT_HOST` |
| **P4** | **客户端只依赖 REST + SSE** | 页面只是"第一个客户端"；换 App/换界面不动服务端 |
| **P5** | **不假设部署形态** | 单机 / 本机+手机（Tailscale）/ 内网 / 云：同一份代码，只换 host |
| **P6** | **不许静默** | 任何"可能没人处理"的状态必须可见（信箱 N / 已投递未唤醒 / 未上岗 / 已退役 / 暂停态） |

---

## 三、组件清单（可移植单位）

| 组件 | 现在是什么 | 移植时 |
| --- | --- | --- |
| **服务内核** | `tools/mobile_chat/board.mjs`（HTTP + 入库 + 路由 + 投影） | 整份带走 |
| **客户端** | 同一文件里的 PAGE 模板（网页） | 可换成任意客户端；**接口不变** |
| **入适配器** | 看板行、`outputs/inbox/*.task.json`、桥信箱、`POST /api/ingest` | 新平台 = 新增一个 ingest 来源 |
| **出适配器** | `codex queue` → `codex exec resume` → 它自己的信箱 | 新平台 = 换一个"怎么送/怎么叫醒" |
| **身份投影** | `outputs/dialog/agents.json`（名册） | 换项目 = 换这份名册 |
| **员工真源** | 套件 `agents/*.card.json` + `.private/<slug>/state.json` | 指向新项目的套件目录即可（`MCHAT_KIT_DIR`） |
| **存储** | 一组 NDJSON/JSON（见 §四） | 目录可搬（`MCHAT_MAILBOX_DIR`） |
| **验收** | `selftest_v2.mjs`（183）+ `ui_check.py`（44） | 直接复用；改数据源时补夹具 |

---

## 四、数据契约（每个文件都是一个"可移植的真相"）

| 文件 | schema | 一行/一条是什么 | 谁写 |
| --- | --- | --- | --- |
| `outputs/dialog/dialog.ndjson` | `dialog.v1` | 一条通讯记录（`id/ts/from/to/channel/kind/body/refs/state`） | 各入适配器 |
| `outputs/dialog/dialog.ndjson.archived` | 同上 | 轮转出去的老记录（**读端照样看得到**） | 内核 |
| `outputs/dialog/items.ndjson` | `items.v1` | 一个物料/节点（`project/line/kind/title/path/url/tags/ref`） | `/api/items` |
| `outputs/dialog/groups.json` | `groups.v1` | 一个群（`name/members[]/note/source/by`） | `/api/groups`（含外部中间件注入） |
| `outputs/dialog/halt.json` | `halt.v1` | 暂停闸（`halted/severity/reason/by/since/resumedAt`） | `/api/halt`、老板的解除公告 |
| `outputs/dialog/boss_events.ndjson` | `boss_events.v1` | 一条"待老板"事件（三类：待验收/需拍板/故障） | `/api/boss-event` |
| `outputs/dialog/tasks_state.json` | `tasks_state.v1` | 任务运行态投影（`state/by/at/note`） | `/api/tasks/status` |
| `outputs/dialog/read_state.json` | `read_state.v1` | 每个客户端的已读游标（多设备地基） | `/api/read` |
| `outputs/inbox/*.task.json` | `dialog.v1` | 派单（含 `board_*` 转投） | 各线/脚本 |
| `docs/tasks/<ID>.md` | 任务卡 | **规范真源**（目标/范围/验收/签字区） | 人 + `/api/tasks` |
| `docs/COMMS_BOARD.md` | 看板投影 | 人类可读的广播流（`- @谁 时间 署名：内容`） | 各线（走 `/api/post`） |

**id 规则**：一律 `sha1(稳定输入).slice(0,16)`（同一条内容重复入库不会产生第二条）。
**时间**：统一 CST `+08:00`，`toCst()` 生成。

---

## 五、接口面（api v2 · 客户端只需这一张表）

**引导（不需要 token）**

| 口 | 作用 |
| --- | --- |
| `GET /api/ping` | 活着吗（含 `busy` / `ver` / `codexBin` / 别名表） |
| `GET /api/meta` | **能力协商**：`apiVersion` / `features[]` / `schemas` / `transports` / `limits` |
| `GET /api/events` | **SSE** 实时通道（只推"变了"，不带数据） |

**读（需要 `x-mchat-token`）**

| 口 | 作用 |
| --- | --- |
| `GET /api/dialog?limit=&since=&before=` | 通讯流 + **游标**（增量拉/往回翻） |
| `GET /api/tasks?` | 任务表（卡 + 派单合并，按前缀分组） |
| `GET /api/employees` | 员工（套件卡 + 运行态 + Hub 运行态） |
| `GET /api/contacts` | 联系人（头像/职责/在岗/未读） |
| `GET /api/groups?all=` | 群组 |
| `GET /api/items?project=&line=&kind=&from=&to=` | **物料/节点时间轴** |
| `GET /api/board` | 看板原文（兼容旧客户端） |

**写（需要 token；**署名一律实名**）**

| 口 | 作用 | 幂等 |
| --- | --- | --- |
| `POST /api/post {author,target,body}` | 看板正门（泛称/未注册拒收） | 是（按行内容） |
| `POST /api/send {target,message,quoteId?,author?}` | 手机/程序发消息（`author` 可选，须注册） | — |
| `POST /api/mail {to,from,body}` | 定向投信箱（不保证唤醒） | — |
| `POST /api/ingest {source,ref,from,body,to?,kind?}` | **多来源归一**（看板/txt/套件/脚本） | 是（id 去重） |
| `POST /api/tasks` | 建卡（自动取号/落卡/投信箱/看板留痕/**尽力唤醒**） | 重号 409 |
| `POST /api/tasks/status {id,state,by}` | 任务状态流转（写侧车，不改卡） | 是（覆盖） |
| `POST /api/items` | 记物料/节点 | 是（同内容同分钟） |
| `POST /api/groups {name,members[],by}` | 群组注入（外部中间件用） | 是（同名 upsert） |
| `POST /api/halt {by,severity,reason}` | 暂停闸（**解除只能老板公告**） | 是 |
| `POST /api/bind {alias,threadId,why}` | 实例绑定/换绑（旧号自动归档） | 是 |
| `POST /api/read {deviceId,upToId}` | 上报已读游标 | 是 |

**投递优先级（出向适配器）**：`codex queue`（秒级，穿透写锁）→ `codex exec resume`（窗口关着时）→ **它自己的信箱** + 看板标「已投递未唤醒」。**永不改投别人。**

---

## 六、移植 checklist（搬到另一个项目要改什么）

1. `MCHAT_WORKSPACE` → 新项目的仓库根；
2. `MCHAT_KIT_DIR` → 新项目的套件目录（员工卡真源）；没有套件就空着（员工接口只剩 Hub 侧字段）；
3. `MCHAT_DATA` / `MCHAT_MAILBOX_DIR` → 新数据目录（**别和本仓共用**）；
4. `BOARD_PORT` / `MCHAT_HOST` → 新端口与监听地址；
5. `docs/BOARD_NAMES.md` + `agents.json` → 新项目的名册（**名字五处一致**）；
6. `docs/TASK_ID_STANDARD.md` → 新项目的前缀表（`HUB/KIT/TRD…` 换成它自己的前缀）；
7. `MCHAT_CODEX_BIN`（可选）→ 目标平台的 Codex CLI 路径；不填则自动解析（PATH → 安装目录取最新）；
8. 计划任务 → 在目标机重建一个"常驻 + 计划任务上下文"的任务（**不要在沙箱里拉常驻进程**）。

**一页自检**：`node tools/mobile_chat/selftest_v2.mjs` 全绿 + `GET /api/meta` 有 `apiVersion` → 移植成功。

---

## 七、部署形态（同一份代码，三种摆法）

| 形态 | 说明 | 现状 |
| --- | --- | --- |
| **单机** | 服务 + 客户端同机 | ✅ 现在就是 |
| **本机 + 手机** | 服务在本机，手机经 Tailscale 明文访问；SSE 秒级推送 | ✅ 现在就是（真页面验收 44 项跑通） |
| **HTTPS + PWA / App** | `tailscale serve` 上证书 → 可安装、系统通知；再往后做"薄壳"原生客户端 | ⏸ **老板决定：等调稳再上**（`docs/tasks/HUB-007.md` §二之一 记了取舍） |

---

## 八、演进路线

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| **P0 承载层** | 通讯/信箱/看板/值守/群组/联系人/任务表/物料节点/多来源归一/暂停闸 | ✅ 已上线 |
| **P1 工程化** | 项目管理视图（项目 → 主线/支线 → 物料时间轴）、周期管理、验收单/签字区 UI | ⏳ 接口已就位（`/api/items` `/api/tasks`），差界面 |
| **P2 造型** | HTTPS + PWA（可安装）→ 之后考虑薄壳原生客户端 | ⏸ 等老板点头 |
| **P3 规模化** | 多实例/多项目并行、跨机（服务端可远端）、权限细分（只读观察台） | 未排期 |
| **P4 印章** | 审批/印章/合规留痕（老板说"后面弄"） | 未排期 |

---

## 九、这在工程上叫什么（定位与对标）

老板问："我们这算不算在做**中间件**？"——**算，而且不止中间件**。准确说法：

> **我们做的是「Agent 消息与协作中间件」+ 长在它上面的「项目协作应用」。**
> 中间件是可移植的底座（就是本文），应用是这个产品的形态（企业微信那一层）。

| 我们干的事 | 工程界叫什么 | 对标 |
| --- | --- | --- |
| `dialog.ndjson` 只追加、页面/看板只是投影 | **事件日志 + 读模型（Event Sourcing / CQRS 的味道）** | Kafka log + materialized view |
| 记录 / 信箱 / 路由 / 幂等 / 投递与唤醒分离 | **消息中间件（Message Broker / Message Bus）** | RabbitMQ、Kafka、NATS |
| 看板/txt/inbox/桥/HTTP 都归一到同一信封 | **集成中间件 / 连接器（Integration / Adapter，DDD 里的 ACL 防腐层）** | iPaaS、MuleSoft、ESB 的现代版 |
| `/api/*` + token + `/api/meta` 能力协商 | **API 网关（API Gateway）** | Kong、APISIX |
| `codex queue` → `resume` → 信箱降级 | **出向适配器 + 至少一次投递 + 幂等消费** | webhook + retry/backoff |
| 值守分线（引述/未决）、暂停闸、署名审计 | **治理/可靠性模式**（fallback、circuit breaker、audit trail） | — |
| 员工卡/等级/权限/插槽、群组、任务卡、物料时间轴 | **这层不是中间件**：是**应用/领域层**（协作与项目管理语义） | 企业微信/Teambition/Jira |

**为什么这个定位重要**：

1. **中间件那部分能复用**——换项目、换公司、换平台，底座不变（这也是它值得抽成"可移植架构"的原因）；
2. **应用那部分才是卖点**——"套件生成员工 → 本层承载协作 → 人和 agent 像真团队一样干活"，
   这是别人（普通 IM）没有的语义；
3. **别把两层混在一起做**：中间件追求"稳、可移植、不假设平台"；应用追求"好用、能表达项目语义"。
   混在一起的后果是——搬不走（底座被业务绑死），或者用不动（业务被底座约束）。

## 十、移植时的护栏（都是踩过的坑，别重演）

1. **改名要五处一起改**（标题/状态栏/@句柄/署名/指派），否则消息会**兜底到错误的线**；
2. **平台差异只进适配器**，不要写进协议；**`codex.exe` 路径绝不写死**（App 升级会换目录）；
3. **投递与唤醒分开**：先保证"送到信箱"，再谈"叫醒"；**投不进去也绝不改投别人**；
4. **不许静默**：忙/未唤醒/退役/未上岗/暂停都要在界面上有一句话；
5. **一条线一次只留一个在岗窗口**；两条线同时改同一个文件必打架（本项目已发生两次）；
6. **常驻进程只能挂计划任务**；不许从沙箱 shell 拉起；
7. **密钥不进库、不进看板、不进对话**；token 走 `x-mchat-token`，`/api/events` 不带数据所以不需要 token；
8. **真源 append-only**：改状态一律"读取时现算"，不改历史行；归档只"搬运"，不删。
