# 承接（换人）运行手册 · 2026-09-12 老板认可

> 🔖 **按级别读**：先跑 `node tools/mobile_chat/whoami.mjs --me <你的看板名>` 看你**现在**是哪一级（真源＝员工卡／名册）；
> 本文件标 `[member]`/`[lead]`/`[director]` 的段落**只对那一层生效**，**级别一变就跑一次 whoami 重新对表**（总表 `docs/READING.md`）。

> 一句话：**岗位不变、工号换代、资产转交、账目分开。**
> 老板原话："旧员工归档以后 slug 变了就不好追溯了……我们的员工 ID 跟 slug 要保持一致，这样才好追溯。
> 新员工用新的 slug，但他只要能继续用通讯软件、继承那些文件就行。"

## 一、三个名字，别混

| 名字 | 是什么 | 能不能变 |
| --- | --- | --- |
| **看板名**（如 `codex-套件`） | **岗位**：给人看、通讯录用、@用 | 延续不变（换人写进传承记录） |
| **slug**（如 `codex-kit` → `codex-kit2`） | **工号**：信箱 / 员工卡 / 私人夹 / 历史账目的索引 | **永不复用**，换人 = 换号 |
| **threadId**（uuid） | **实例**：某个对话窗口 | 随时换，旧的进 `failedThreadIds` |

**为什么工号必须换**：追溯。老工号的历史永远属于老员工，新员工的账从零开始，
中间由一条**承接记录**（`outputs/dialog/successions.ndjson`）把两代连起来。

## 二、六步流程（只有第 0 步是人做的）

| # | 谁做 | 做什么 | 判据 |
| --- | --- | --- | --- |
| **0** | **老板** | 在 UI **手动**新建一个窗口（项目/工作区选对；**不要用工具建**，建坏过） | 拿到新 threadId |
| 1 | 旧员工 | 写**交接文档**（模板 `docs/SUCCESSION_TEMPLATE.md`） | 四节齐全：身份 / 工位 / 未结单据 / 别再做什么 |
| 2 | 脚本 | **门禁**：交接文档不合格就拒绝换人 | `--plan` 输出"✓ 计划可执行" |
| 3 | 脚本 | 名册：新工号占岗位名、旧工号退役（只标记不删，旧号进 `failedThreadIds`） | `agents.json` 出现 `·退役` 条目 |
| 4 | 脚本 | **信箱转交**（只转未读）+ **私人夹复制**（复制不删） | 新信箱有 `refs.transferredFrom` |
| 5 | agent/平台 | **先改名、后归档**：旧窗口 `setName「[已归档] 原名·日期」`→ 再 `archive`；新窗口 `setName「岗位名」` | `thread/setName` + `thread/archive` |
| 6 | 新员工 | 唤醒后自检六步 → 回板一句"我在" | 看板出现实名一行 |

> **顺序不能反（2026-09-12 实测）**：`set_thread_title` 对**活线程**有效（本线实测改名成功）；
> 对**已归档**的线程会报 `no rollout found for thread id`（rollout 已移到 `archived_sessions\`）。
> 所以要**先改名、后归档**，否则那口锅就一直挂着旧名字，追溯时看不出它已退役。

## 三、命令

```powershell
node scripts\crew_succession.mjs --selftest
node scripts\crew_succession.mjs --plan --board codex-套件 --old-slug codex-kit --new-slug codex-kit2 --handover docs\SUCCESSION_codex-kit_20260912.md --new-thread-id <新uuid> --reason "换到 D: 工位"
node scripts\crew_succession.mjs --apply <同上参数>      # 真跑，先备份 agents.json
node scripts\crew_succession.mjs --trace codex-套件 "2026-09-12 21:00"
```

## 四、铁律

1. **没有交接文档，不许换人**（脚本硬拦）；
2. **工号永不复用**——新员工一律 `-2`、`-3` 递增，不许拿旧号；
3. **私人夹只复制不删**：旧的是"这个员工在这台机器上存在过的证据"；
4. **信箱只转未读**：已读的是旧账，留在旧信箱里当历史；
5. **批文归卡不归线**：签字留在任务卡上，已签的不许再签第二遍；
6. **会话上下文不转**（刻意）——新员工靠交接文档 + 未结单据清单重建。

## 五、追溯怎么查

每条消息只带"看板名"，所以"这句话是哪一代说的"要这样查：

```powershell
node scripts\crew_succession.mjs --trace <看板名> "<时间>"
```

承接记录是 append-only 的 `outputs/dialog/successions.ndjson`，含：
`ts / board / oldSlug / oldThreadId / newSlug / newThreadId / reason / handover / by / movedMail`。

> 后续增强（未做，已提给看板编辑）：落板时给消息补 `refs.slug`，那就不必再靠时间推断。

## 六、两个已定的口径（2026-09-12 与看板编辑对齐）

1. **`<看板名>·退役` 是"退役档案条目"，不是一个真人**：它在名册里只作档案（`status=retired`、无 `threadId`），
   **不投递、不代答、不兜底、不计入在岗**；界面上灰显而不是消失（可追溯）。名字表口径由 `docs/BOARD_NAMES.md` 的 owner（看板编辑）落。
2. **`slugAliases` 只用于"识别旧 slug 并回绝"，不做正向解析**——@旧工号会被 400 拒并指路"请用岗位名 @X"。
   理由：**把给旧人的话自动送给新人，是另一种冒名**。
