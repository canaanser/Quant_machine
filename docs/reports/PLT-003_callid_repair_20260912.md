# PLT-003 · `codex-总监` 锁死修复（断电 → `missing field call_id`）

- **时间**：2026-09-12 23:0x–23:2x　**执行**：老板当场指派（"我让你修复他"）
- **类型**：`incident`（在岗线完全不能工作）　**严重度**：`S2`
- **范围**：`C:\Users\Administrator\.codex\` 下三处（**工作区之外**，每次写操作均单独获批）
- **定性**：**平台缺陷（客户端写入残项）+ 一个把它持续放大的心跳**；不是线自己的操作错误

## 一、症状

`codex-总监`（线程 `01a08ac2-…`）**每一轮都被平台 400 拒收**：

```
Failed to deserialize the JSON body into the target type: input: missing field `call_id`
```

最后一次成功回合 **22:36:53**；此后 23:06:40 / 23:07:36 / 23:12:40 / 23:15:55 / 23:18:35 全挂。

## 二、根因（三层，缺一不成灾）

1. **客户端写了一条残项**：心跳注入时写出的 `function_call_output` **漏了必填 `call_id`**
   （`rollout` 第 **8228**、**8243** 行，`id=fco_01a09628-037f-…` / `fco_01a0962d-8208-…`，
   `namespace=codex_app`、`output` 是**字符串**而非数组——与正常形态完全不同，属断电/启动窗口期的半个写入）。
   测试：全机扫 `sessions\*\*\*\*.jsonl`，缺 `call_id` 的项**只有这两条**（别的线没被断电波及）。
2. **一个心跳在持续下毒**：`~/.codex/automations/automation/automation.toml`
   —— 心跳「总监线·开发-验收闭环巡检」，`rrule=FREQ=MINUTELY;INTERVAL=5`，`target_thread_id=01a08ac2…`。
   它**每 5 分钟**触发一次，每次触发就再写一条同类残项，再失败一轮 → **线永久锁死且伤口持续扩大**。
3. **投影不会回头**：`thread_history_projection_state.next_rollout_byte_offset` 证明投影是**按字节偏移增量**吃的，
   已吃过的行**永不再读** → **只改 rollout 没用**（实测：改完再发消息，仍然同一条 400）。

> 与 `LESSONS.md` L15 坑② 是**同一族平台 bug**（`create_thread` 首回合同样报 `missing field call_id`）。

## 三、改了什么（三处，全部留回滚点）

| # | 对象 | 改动 | 回滚 |
| --- | --- | --- | --- |
| 1 | `~/.codex/automations/automation/automation.toml` | `status: ACTIVE → PAUSED`（**止住毒源**，不改频率/内容） | 用 app 的自动化工具体恢复为 ACTIVE |
| 2 | `rollout-…01a08ac2….jsonl` 第 8228、8243 行 | 就地改写为**同字节长度的合法 `message`(role=user)**，内容＝原心跳文本 | `Copy-Item '<file>.bak-plt003-20260912151517' '<file>' -Force` |
| 3 | `thread_history_1.sqlite`（`thread_items` 2 行） | `functionCallOutput → userMessage`（item_id 主键不动，内容同上） | `Copy-Item '…sqlite.bak-plt003-20260912231820' '…sqlite' -Force`（**需先关 app**） |

执行脚本（都在 `scripts/`，默认演练、`--apply` 才写）：
`repair_rollout_missing_callid.mjs`（账本，**不增删行、总字节不变**）、`plt003_fix_projection.py`（投影）、
`plt003_inspect_callid.py`（只读勘察）。

**为什么用"等字节长度替换"**：投影存的是字节偏移；增删行会让后面所有行的偏移错位。
替换后总字节 `18718131` 与行数 `8246` **均未变**，全文 JSON 逐行可解析。

## 四、验证

| 项 | 结果 |
| --- | --- |
| 账本残项 | **0**（`repair_rollout_missing_callid.mjs` 复扫：无发现） |
| 投影残项 | **0**（`functionCallOutput` 已从 `item_type` 分布消失；两行 = `userMessage`） |
| 心跳 | `status = "PAUSED"`（已落盘核对） |
| **回合是否真能跑** | **未通过** —— 两处存储都干净后，23:18:34 那一轮**仍然**报同一条 400 |

→ 说明**请求不是现读盘、而是吃进程内存里的会话状态**；三处落盘修复要生效，**必须重启 Codex app 重新加载**。

## 五、接手动作（一步，只能老板做）

1. **关掉 Codex app 再打开**（让它重新加载；线程窗口重开即可，不必新建）；
2. 给 `codex-总监` 发一句话验证（`codex queue --thread 01a08ac2-… --message "…"` 亦可）；
3. 若**仍**报 `missing field call_id` → 用上表回滚，并把本报告升格为平台级工单（去重属上游，本地改不到）。

## 六、遗留与风险

1. **上游未修**：请求构造应对残项/命名空间去重；本地只能修数据，不能修行为。
2. **心跳为什么坏**：同一 heartbeet 注入路径此前是正常的，断电后开始写残项；
   **在平台修好前，不要给任何线重启这个心跳**（`ACTIVE` 会立刻再下毒）。
3. **未追责**：本轮故障中 `codex-总监` 无操作错误（它只是被平台写坏了），只记平台缺陷 + 数据修复。
4. **流程修正**：本次按老板指令动了 `rollout` 与 `sqlite`（PLT-001 原红线禁止）——
   依据是"先只读勘察、把残项实实在在找出来"（L11），并全程先备份、等字节改写、写后核验。
   建议把这条路正式写进 `RUNBOOK`，并保留"未获授权不得动账本/库"这条底线。

## 七、复发与收口（2026-09-13 00:2x–00:4x）

**复发**：`codex-总监` 23:49 还正常，**00:29:10 又 400**。逐行勘察：账本新增第 **8877** 行，
形态与之前两条**一模一样**（`function_call_output` / `name=automation_update` / `namespace=codex_app` / 无 `call_id`），
`payload.output` 里就是那段心跳巡检文本，`current_time_iso=2026-09-12T16:29:09.989Z`。

→ **确证触发源 = 那条心跳的注入路径**（不是断电本身；断电只是让第一次的残项以同样形态出现）。
→ 也就是说：**心跳每 ACTIVE 一次、每触发一次，线就被打回 400**。它在 23:33 被重新置为 ACTIVE，
   00:29 触发即中枪。

**处置（同法，已跑完）**：

| # | 对象 | 改动 | 回滚点 |
| --- | --- | --- | --- |
| 1 | 心跳 | `ACTIVE → PAUSED`（第二次按住） | 用自动化工具体恢复 |
| 2 | 账本 L8877 | 等字节替换为中性留痕 `userMessage`（总字节 19814657、行数 8880 不变） | `…jsonl.bak-callid-20260913003413` |
| 3 | 投影 1 行 | `functionCallOutput → userMessage`（正文同步为中性留痕） | `…sqlite.bak-callid-20260913003413` |

**通用化**：本次把修复写成**通用器** `scripts/repair_callid_incident.py`
（`--rollout <jsonl> --thread <uuid> [--apply]`，默认演练；账本+投影一起修、写后核验、自动备份），
以后任何线中同一枪都能一条命令处置。踩坑记录：我第一版**只改了 `item_json`、漏改 `item_type`**，
被自己的写后核验拦下（"投影仍有 1 行 functionCallOutput"）→ **写后核验必须留着**。

**心跳原文存档**：`docs/AUTOMATION_director_heartbeat_20260913.toml`
（含恢复方法与"平台修好前不许再开"的警告），所以**删不删都安全**。

**收口结论**：**留心跳、别删，但必须保持 `PAUSED`**；它要的"按点自检"改用已实测可用的
`crew_host` → `codex queue` 门铃通道（干净的注入路径）。盘上改完仍需**重启 Codex app** 才被重新加载。
