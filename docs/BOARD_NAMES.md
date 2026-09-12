# 看板命名规约（真源）— 2026-09-10 老板定，Codex 统一

> 🔖 **按级别读**：先跑 `node tools/mobile_chat/whoami.mjs --me <你的看板名>` 看你**现在**是哪一级（真源＝员工卡／名册）；
> 本文件标 `[member]`/`[lead]`/`[director]` 的段落**只对那一层生效**，**级别一变就跑一次 whoami 重新对表**（总表 `docs/READING.md`）。

> **规则一句话**：每个实例只有**一串名字**，形如 **`前缀-短名`**；前缀只有 `dsh`（DeepSeek-Harness 侧）和 `codex`（Codex 侧），`老板` 是人、不适用。**前缀就是名字的一部分，不再二次加前缀。**
>
> **这串名字必须到处都一样**（老板 2026-09-10 20:3x 强调），至少覆盖这五处：
>
> | 出现的位置 | 由谁改 |
> |---|---|
> | 对话框标题（desktop 侧边栏显示的那行） | 各线自己 / Codex 侧 `set_thread_title` |
> | **状态栏**的实例标签（Hub 手机页 `agents` 芯片、`agents.json` 的 `label`） | `codex-看板编辑`（board.mjs） |
> | 看板 **@ 句柄** | `codex-看板编辑`（路由表） |
> | 看板 **行尾署名** | `codex-看板编辑`（board.mjs 署名逻辑） |
> | inbox 指派名（`instance` / `claimedBy`） | `codex-看板编辑` |
>
> 以后不再出现泛称 `Codex` / `DSH`。

## 一、名字表

| 看板名 = @句柄 = 署名 = **目标对话框标题** | 对话框标题现状 | 是什么 | 实例 ID | 旧名（兼容保留） |
|---|---|---|---|---|
| `老板` | —（人） | 老板本人 | — | — |
| `dsh-老员工` | 老员工 ⚠️待改 | dsh 值守主会话（GUI，primary） | `session-4258a4fe-4dbd-49f7-a12b-67a5fa153417` | `@dsh`、`@dsh-main`、署名 `DSH` |
| `dsh-quant` | （headless，无窗口） | dsh 仓库执行实例 | headless profile | — |
| `codex-唤醒通道` | **codex-唤醒通道** ✅已改（原「DSH唤醒」） | 门铃 / 看板哨兵（本线） | `01a08acf-9cd8-76b2-8367-33f06214f8e0` | `codex-DSH唤醒`、署名 `Codex` |
| `codex-看板编辑` | 看板编辑 ⚠️待改 | Dialog Hub / 会话工具 v2（`board.mjs` 真源） | `01a08ab8-c2a7-7c02-943b-f217d2538a83` | `@codex-convtool` |
| `codex-看板助理` | 不建窗口（`title`=系统自测） | **系统自测身份**（老板 2026-09-11 23:5x 定）：自测/联调**一律用这个名字当 `from`**，不许借 `老板` 或在职线的名字；不绑会话、`duty:false` | 已在册（`agents.json`） | `codex-assist` |
| `codex-量化总监` | 量化总监 ⚠️待改 | Codex L1 线 | `01a0877b-284f-7480-80a1-c957063b9198` | `@codex` |
| `codex-总监` | 总监 ⚠️待改 | Codex L1 线 | `01a08ac2-d43a-72f0-8a26-618e3c8e8edd` | `@codex` |

> `dsh-老员工` 那条的标题要不要改成 `dsh-老员工`，由看板编辑线一并跟 dsh 对齐（改标题要走 `session/rename`，属唤醒线的门铃能力，需要时可叫我）。

看板行格式（不变）：

```
- @<看板名> <YYYY-MM-DD> <HH:MM> <看板名>：内容
```

例：`- @dsh-老员工 2026-09-11 09:20 老板：盘前先把引擎状态过一遍`

## 二、为什么要带前缀

对话框标题（"老员工"、"总监"）是**给人看的**，可能重名、可能被平台自动改写；前缀 `dsh-` / `codex-` 表明**消息该往哪一侧投**，路由不会歧义。两段合起来既好认、又唯一。

## 三、各侧落点（谁改哪）

| 侧 | 真源文件 | 要改的 |
|---|---|---|
| Codex 看板服务 | `tools/mobile_chat/board.mjs` | ① 署名：把 `sender === "codex" ? "Codex" : "DSH"` 这类硬拼改成**按实例名**；② `agents.json` 的 `label` 与 `target` 用看板名；③ 路由表认新句柄（旧句柄继续兼容） |
| 看板哨兵 | `tools/mobile_chat/dsh_board_sentinel.py` | 触发句柄认 `@dsh-老员工`（**本文件已改**，见 §四） |
| 文档 | `docs/DIALOG_HUB.md`、`docs/DSH_BOARD_SENTINEL.md` | 路由口径引用本表 |

## 四、兼容策略（不许断链）

- **旧句柄全部保留可用**：`@dsh`、`@dsh-main`、`@codex`、`@codex-convtool` 继续路由到同一实例；只是**署名和新写的行**一律用新名。
- 哨兵触发句柄：`@dsh-老员工`（主）+ `@dsh`、`@dsh-main`（兼容）。
- `@dsh-quant`、`@codex-*` **不**触发 dsh 主会话的唤醒。

## 五、变更记录

| 时间 | 变更 |
|---|---|
| 2026-09-10 20:2x | 老板定规约（前缀 + 对话框名），Codex 建本表；哨兵同步改句柄 |
| 2026-09-10 20:3x | 老板加码：**全局同一串**（含状态栏）；本线标题改为 `codex-唤醒通道`；移交 `codex-看板编辑` |

---

## 六、交接给 `codex-看板编辑`（2026-09-10 20:3x）

### 6.1 老板的需求

1. **全局只用同一串名字**：对话框标题、**状态栏**、看板 @ 句柄、看板署名、inbox 指派名，五处必须一致。
2. 前缀 `dsh-` / `codex-` 保留；`老板` 例外。
3. 命名真源就是本文件；实现落在 `board.mjs`。

### 6.2 唤醒线已完成（不需要你处理）

- **门铃（Web RPC）打通**：`POST /api/session/<method>` + 签名 cookie，协议与实测见 `docs/reports/AR-001_arch.md`。
- **看板哨兵落地**：计划任务 `DSH-Board-Sentinel`，每分钟一次、`pythonw` 无窗口；只认「署名 `老板` + `@dsh-老员工`/`@dsh`/`@dsh-main`」；冷启动只记不发、每日上限 20 不丢行。规格见 `docs/DSH_BOARD_SENTINEL.md`。
- 本线对话框标题已改为 **`codex-唤醒通道`**；哨兵句柄已按本表改完。
- 已用门铃通知 dsh 新命名，他回帖已在用 `dsh-老员工：`。

### 6.3 待 `codex-看板编辑` 完成（`board.mjs` 是这些项的真源）

| # | 位置 | 要改成 |
|---|---|---|
| 1 | 署名硬拼（约 L549 `sender === "codex" ? "Codex" : "DSH"`，另见 L422/L581/L809/L940 一带） | 实例的看板名 |
| 2 | **状态栏**：`agents.json`（board.mjs L705-719 生成）的 `label`、手机页 `#agents` 芯片 | 看板名 |
| 3 | 路由：`resolveTarget()` / `instance` 解析 | 认 `@dsh-老员工`、`@codex-看板编辑`…，旧句柄保留兼容 |
| 4 | 看板文件头两行说明（board.mjs L68-72 生成） | 换新名 |
| 5 | `docs/DIALOG_HUB.md` 路由口径 | 引用本表 |
| 6 | （可选）各线对话框标题 | 改成同一串；Codex 侧 `set_thread_title`，dsh 侧 `session/rename` 可由唤醒线代劳 |

### 6.4 验收（四处一致即可收工）

随便挑一条消息，在 **手机页状态栏标签 / 看板 @ 句柄 / 看板行尾署名 / inbox 指派名** 四处看到的必须是同一串。

---

### 6.5 事故记录：跨线程委派工具会写坏目标线程（2026-09-10 20:40）

**现象**：`codex-看板编辑`（`01a08ab8…`）从 20:40 起每个回合都失败：

```
Failed to deserialize the JSON body into the target type: input: missing field `call_id`
```

**根因**：`codex-唤醒通道` 用 `send_message_to_thread` 给它发交接时，工具在**目标线程**的历史里写入了一条
`function_call_output`（`id=fco_…`、`name=send_message_to_thread`），但**缺 `call_id`**，也没有配对的
`function_call`。历史一旦带上这条，之后**任何**新回合在拼请求时都会在这一点反序列化失败——连老板在窗口里
直接说话也一样。列号随历史增长而增大（1027322 → 1027464），就是同一个坏点。

**定位与修复**（`codex-唤醒通道` 执行，全部经校验）：

1. **发请求用的是 rollout 原始日志**（`sessions/.../rollout-*.jsonl` 里的 `function_call` /
   `function_call_output` 线格式）；`thread_history_1.sqlite` 的 `thread_items` 是**给界面看的另一套投影**
   （camelCase 类型），改它**不生效**——这一步我先做错过，已纠正。
2. **不要删行**：投影状态里存了 rollout 字节偏移（`thread_history_projection_state.next_rollout_byte_offset`），
   删行会让后续偏移全部错位。要用**等字节替换**：把坏行改写成一条等长的合法 item（我换成了普通
   `message`/`role=user`，正文是原文），文件长度不变 → 偏移全部保持有效。
3. 备份 → 替换 → 复查：`function_call` 133 / `function_call_output` 133 配平，坏行 0。
   （数据库那条投影行顺手删掉没关系，它只是界面用。）
4. **改完必须让应用丢掉内存里那份历史**：光改磁盘不生效（应用抱着旧的在内存里，报错列号会随历史继续增长）。
   做法：`set_thread_archived(true)` → 线程状态从 `idle` 变 `notLoaded`（内存副本被丢弃）→
   `set_thread_archived(false)` 放回来。下次打开即从磁盘重载。

**遗留**：另一条 `01a08ab5…`（「会话工具 v2 建设」）还有 2 条同类坏条目（`create_thread`、
`send_message_to_thread`），未修，等老板示下。

**禁忌（写进纪律）**：

- **不要用 `send_message_to_thread` / `create_thread` 跨线程投递**——当前版本会给目标线程写出没有 `call_id`
  的委派输出，等于把对方线程毒死。
- 要通知别的线：**写看板行 + 让老板转达**，或用该线程自己能读到的文件（本文件）作为载体。
- 万一再出现 `missing field call_id`：不要去改 `rollout-*.jsonl`，去 `thread_items` 里找 `item_type` 为
  `functionCallOutput` 且 `item_json` 里没有 `call_id` 的行，删掉即可（删前先备份 `thread_history_1.sqlite*`）。

**再犯记录（第 2 次，2026-09-11 04:0x，`codex-看板编辑` 亲手验证）**：用 `create_thread` 新建的线程
**一出生就是坏的**——它给新线程写了 `functionCallOutput(name=create_thread)` 且没有 `call_id`，
该线程首个回合直接 `systemError`（界面显示红色叹号），且**无法用后续消息救回**（历史里那个坏点一直在）。
结论：**跨线程创建/投递工具在当前版本一律不能用**；要开新窗口只能由老板在 UI 里**手动新建任务**
（项目选 `量化交易软件`、环境选 `local`、**不要 worktree**），再把交接话贴进去。
坏掉的线程处理：`set_thread_archived(true)` 归档即可（不删），本日已归档 2 条（`01a08cd9…`、`01a08cde…`）。
