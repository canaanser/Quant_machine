# 平台私有面「可探测 + 可降级」探测点清单（A 阶段 · 只读）

- **卡**：A 阶段（只读盘点），据 `docs/RUNBOOK_KIT_MIGRATION.md` §六 第 1 条；**卡号：待总监取号**（PLT 系；前缀只认登记表里那五个，不自造）。
- **状态**：A 阶段已由 `codex-看板编辑` **验收通过**（2026-09-13 02:55）；本文件按其两条实证做过一次修订（见 §五）。
- **作者 / 时间**：`codex-适配`（工号 `codex-adapter`）／2026-09-13。
- **范围**：`E:\stockgate\Quant_Alpha_System` 内**代码与脚本**（`tools/`、`scripts/`、`config/`、`run/`、`duty/`）；文档只作旁证。
- **纪律**：全程只读，未改任何文件、未跑任何 `codex` 子命令、未进别人仓、未碰 `spec/`。
- **判据**：本条按"**不是所有耦合都该消灭**"——只收编**多余耦合**（把平台私有面当 API、把本机路径写死进逻辑）。

## 一、总表（6 条探测点）

| # | 私有面 | 落点 | 形态 | 探不到时的降级 | 验证状态 |
| --- | --- | --- | --- | --- | --- |
| P1a | codex.exe 解析 | `tools/mobile_chat/server.mjs:11` | **版本哈希写死** | 无（直接 ENOENT） | **已复核为真缺陷**（见下） |
| P1b | codex.exe 解析 | `tools/mobile_chat/board.mjs:18-47` | 三级解析（env→PATH→安装目录取最新） | 返回空串并在日志报一行 | 代码已读，未实跑 |
| P1c | codex.exe 解析 | `scripts/crew_host.py:269-273` | 只扫安装目录取最新 | 返回 `None`→ 当轮跳过 | 代码已读；**收编方向已由看板编辑提交总监** |
| P2 | `codex queue` | `board.mjs:397-411`、`crew_host.py:276-284` | 唤醒主通道 | 退 `resume`；再不行报失败 | **已实证**：退出码 0 = 受理 ≠ 起回合（见 §五①） |
| P3 | `codex exec resume` | `board.mjs:451-455`、`server.mjs:145-148`、`crew_host.py:299-315` | 唤醒备选通道 | 只落信箱，**不当"已唤醒"** | 有反向实测（见 §三） |
| P4 | `thread-writer-locks` | `board.mjs:186,2065-2072`、`crew_host.py:287-296` | 写锁探测 | 锁判"未知"，改"真投一次看结果" | 有历史裁决（见 §三） |
| P5 | `app-server` | 无调用点；仅探针 `scripts/plt002_doorbell_probe.ps1:35-41`、`plt002_pipe_probe.ps1` | 协议层能力 | 不存在即降级 → 纯信箱模式 | 历史判死，未复验 |

## 二、逐条证据（行号 + 原文摘录）

### P1a —— `server.mjs:11` 版本哈希写死（真缺陷）

```
11: const CODEX = "C:\\Users\\Administrator\\AppData\\Local\\OpenAI\\Codex\\bin\\fd4c151a749f3ab4\\codex.exe";
```

同文件第 145-146 行用它跑 `exec resume`：

```
145:     out = await runCodex(
146:       ["exec", "resume", "--json", "--skip-git-repo-check", "-o", LAST_FILE, String(state.threadId), "-"],
```

**判据**：`codex-看板编辑` 复核当前线上版本哈希为 `bffc5354119c8421`，与写死的 `fd4c151a749f3ab4` **不一致** → **这个文件现在就是坏的**。
（`board.mjs:11-13` 的注释已记录同一坑：App 更新后目录从 `fd4c151a…` 变成 `7ac07f4c…`，写死那份直接消失。）

### P1b —— `board.mjs:18-47` resolveCodexBin()（已收敛的正确形态，可作样板）

```
14: //   ① env `MCHAT_CODEX_BIN`（自测指向桩程序 / 手工指定）
15: //   ② PATH（现在 PATH 里就有 codex.exe）
16: //   ③ `%LOCALAPPDATA%\OpenAI\Codex\bin\<版本哈希>\codex.exe` 里**按修改时间取最新**
18: const CODEX_BIN_ENV = process.env.MCHAT_CODEX_BIN || "";
33:       const binRoot = path.join(process.env.LOCALAPPDATA || "", "OpenAI", "Codex", "bin");
39:           if (st.isFile() && (!best || st.mtimeMs > best.mtimeMs)) best = { p, mtimeMs: st.mtimeMs };
46:   if (!found) log("CODEX BIN 解析失败：env/PATH/安装目录都没找到 codex.exe");
```

### P1c —— `crew_host.py:269-273` find_codex_exe()（第二套实现）

```
269: def find_codex_exe():
270:     """找最新的 codex.exe——更新后哈希目录会变，所以每次现找。"""
271:     pat = os.path.join(os.environ.get("LOCALAPPDATA", ""), "OpenAI", "Codex", "bin", "*", "codex.exe")
272:     cands = glob.glob(pat)
273:     return max(cands, key=os.path.getmtime) if cands else None
```

**判据**：与 P1b 是同一件事的**第二份实现**（少了 env 覆盖、少了 PATH 段、无缓存）→ 属"重复实现要收编"。
调用点在 `crew_host.py:331-334`：找不到就 `log("doorbell-queue: 找不到 codex.exe，跳过")` 并当轮返回。

### P2 —— `codex queue`（主通道）

```
402:     const out = await runCodex(["queue", "--thread", tid, "--message", text], "", 30000);
403:     if (out.code !== 0) {
404:       return { ok: false, how: "queue-failed", ms: Date.now() - t0, error: String(out.stderr || "").slice(-200) };
```

```python
282:     r = subprocess.run([exe, "queue", "--thread", thread_id, "--message", message],
283:                        capture_output=True, text=True, timeout=90, env=env)
```

调用前有节流：`board.mjs:397-399`（冷却 + 每小时上限）、`crew_host.py:242-246`（冷却 600s / 单轮最多 2 条 / 每线每小时 20 次）。

**退出码语义（2026-09-13 02:55 由 `codex-看板编辑` 实证）**：`queue` 退出码 `0` 只表示**受理**，**不等于会起回合**——
反面实证是"已投递未唤醒"（桌面端占用 / 队列冷却）：投递成功、回合没起。判据因此写死为**"回合账本出现新回合"**（`thread_turns`）；
**会话文件的 mtime 会滞后，不能当判据**（同一晚已按 mtime 误判过一次）。

### P3 —— `codex exec resume`（备选，**已知会"假绿灯"**）

`board.mjs:451-455`：

```
451:   out = await runCodex(
452:     ["exec", "resume", "--json", "--skip-git-repo-check", "-o", LAST_FILE, String(threadId), "-"],
```

`crew_host.py:318-328` 的注释把结论写明了：

```
320:        · `codex queue` 对"已加载/未加载"两种线**都能真的跑出回合**；
321:        · `codex exec resume` 会**报成功却不产生回合**（查过对方线程 updatedAt 不动）——
322:          所以它只能当备选，不能当主通道。
```

**判据**：这条的降级语义必须是"**报了成功也不算唤醒**"，判据只看对方是否真起回合。

### P4 —— `thread-writer-locks`（写锁）

```
186: const THREAD_LOCKS = process.env.MCHAT_THREAD_LOCKS || "C:\\Users\\Administrator\\.codex\\thread-writer-locks";
2065: function lockPresent(threadId) {
2067:     fs.statSync(path.join(THREAD_LOCKS, String(threadId) + ".lock"));
```

```python
289:     p = os.path.join(os.path.expanduser("~"), ".codex", "thread-writer-locks", thread_id + ".lock")
293:         with open(p, "r+b"):
294:             return False          # 能独占打开 = 没被持有
296:         return True               # 打开失败 = 被持有
```

**判据**：同一私有面的两种定位法（一个写死盘符路径、一个用 `~`）；且 `board.mjs:2060-2064` 已裁决**锁只当线索**——
"锁在 ≠ 有人在跑回合"，判忙以"真投一次、失败算忙"为准。这就是本条要的**降级形态**。

### P5 —— `app-server`（协议层，代码里无调用点）

仅两个**只读探针**：`scripts/plt002_doorbell_probe.ps1:35-41`（列 `~/.codex/app-server-control` 目录）与 `scripts/plt002_pipe_probe.ps1`（只连 `\\.\pipe\codex-ipc`，不写）。
历史结论（`docs/reports/HUB-005_channel.md`）：`app-server proxy` 在 Windows 判死（控制套接字不存在 / 拒绝 / 无人接受），`daemon` 平台不支持。
→ 降级路径已定：**app-server 不可用 → 走 P2/P3 → 再不行纯信箱模式**。

## 三、已排除（附理由，避免下轮重复摸）

| 位置 | 内容 | 为什么不算 |
| --- | --- | --- |
| `tools/mobile_chat/dsh_board_sentinel.py:113` | `return index, "resume"` | 哨兵**读锚点续读**的模式名，与 `codex exec resume` 无关 |
| `outputs/board.mjs.bak-20260911-2340:133,318` | 与 `board.mjs` 同文的旧快照 | 备份副本，不是独立调用点（但**说明缺陷曾被复制**） |
| `docs/DIALOG_HUB.md` / `CONVTOOL_V2_PROGRESS.md` / `LESSONS.md` | 关于 queue / 锁 / app-server 的记录 | 是**记录**，不是调用点 |
| `duty/`、`scripts/register_*.ps1` | `E:\python\pythonw.exe`、`E:\stockgate…` 等 | 属 §六**第 2 条**（宿主硬编码收配置层），**不是本卡**（平台私有面） |

## 四、统一降级口径（建议，供 B 阶段实现）

1. **探不到 codex.exe** → 不唤醒；**明确报一声**（当前两处不一致：`board.mjs:284` 抛错、`crew_host.py:333` 静默跳过）→ 降级为"只落信箱 + 看板记一行"。
2. **queue 不可用** → 退 `resume`；**resume 的结果不算唤醒证据**，只看对方是否真起回合。
3. **两条通道都不可用** → 纯信箱模式（留言落盘，等本人上线自取），并在看板记一行，**不许静默**。
4. **锁目录不可读/不存在** → 锁判"未知"，改"真投一次看结果"。
5. **app-server 不可用** → 与第 3 条同（现网即此形态）。

## 五、未验证项（**不许当"应该能行"**）

> ①④ 两条已于 2026-09-13 02:55 由 `codex-看板编辑` 给确定答案（带实证），**结项**；余下 4 条仍未验。

1. ~~`codex queue` 的退出码语义~~ —— **已结**：`0` = 受理 ≠ 会起回合；判据 = 回合账本出现新回合（`thread_turns`）；**mtime 不可作判据**（实证：02:46 投信 → 02:49:23 起回合，延迟约 3 分钟；反面形态"已投递未唤醒"）。
2. `queue` 在**沙箱内 vs 计划任务上下文**的可达性差异——未验（02:46 那次证明了"有人起回合"，但走的是哪条通道需查投递日志）。
3. `server.mjs` 现在是否仍在生产使用（还是已被 `board.mjs` 取代的旧入口）——未核。
4. ~~解析不到 codex.exe 时有没有兜底~~ —— **已结：有，且是既有链路，不用新造**。`runCodex()` 解析不到 bin → `reject` 并留日志 `CODEX BIN 解析失败：env/PATH/安装目录都没找到 codex.exe`（`board.mjs:283-285`、`:46`）；投递失败后走**落信箱 + 标注**：调度路径 `queueForThread` + 系统行（「已投递未唤醒」）；`/api/mail` 的信**在唤醒之前就已落信箱**，唤醒失败另记 `MAIL WAKE MISS` + 排补投。→ 探测层的降级语义照抄：**"解析失败 → 不算唤醒、但消息不丢"**。
5. 非 Windows（Linux/macOS）下 `thread-writer-locks` 的路径形态——未验（平台当前不支持），B 阶段只能说"Windows 已做，其他未验"。
6. `app-server proxy` 连现有控制套接字——历史判死，**本次未复验**。

## 五之二、重复实现的收编归属（2026-09-13 02:55 口径）

- `board.mjs:20 resolveCodexBin()`（env → PATH → 安装目录取 mtime 最新 + 30s 缓存 + 失败留日志）= 看板编辑认可的**样板形态**；口径 = **全仓只留一处解析**。
- `crew_host.py:269 find_codex_exe()` = 第二份实现。该文件**不在看板编辑手上**（属调度治理 / 总监）→ 由**看板编辑提给总监**，我只把它记进本清单。
- `server.mjs:11` 那条**坏文件**归看板编辑修（它这条线的仓）。
→ **三处我都不动手。**

## 六、B 阶段路径清单（待 `codex-套件` 同意 + 开工令）

拟**只新增**（不改既有文件）：

```
adapters/codex/README.md          平台总览 + 能力矩阵 + 降级口径
adapters/codex/platform.json      默认配置（解释器/路径/锁目录，凭据只给路径）
adapters/codex/probe/index.mjs    能力探测：codex.exe 解析 / queue / resume / 锁目录 / app-server
adapters/codex/wake/index.mjs     投递 + 唤醒（queue 优先 → resume 备选 → 落信箱）
tests/codex-probe.test.mjs        探测与降级的单测（注入假实现）
```

**可复用先例**：`tools/mobile_chat/selftest_v2.mjs:114,700` 已经用 `MCHAT_CODEX_BIN` 指向桩程序（`codex-stub.cmd`）做自测 → 证明"可注入假实现"这条路在现网已跑通，B 阶段直接沿用同一手法。

### 六之二、桩程序注入先例（只读预备，2026-09-13 摸清）

等开工令期间按 `codex-看板编辑` 的建议把先例摸清了，B 阶段照抄即可：

| 要点 | 证据 | 说明 |
| --- | --- | --- |
| 桩程序本体 | `selftest_v2.mjs:112-139` | 一个 `.cmd`：按线程号分支——含 `01a0dddd` → 写回复并退出 0（模拟"唤醒成功"）；含 `01a01111` → 只走 `resume` 能成（验备用路径）；其它 → 抢锁冲突、退出 1（模拟桌面端持锁） |
| 注入方式 | `selftest_v2.mjs:700` | `MCHAT_CODEX_BIN: <桩程序路径>` —— **生产代码一行不改**就能换实现 |
| Windows 注意 | `selftest_v2.mjs:701` | `MCHAT_CODEX_SHELL: "1"`（`.cmd` 在 Windows 下要经 shell；生产默认 `shell:false`，避免注入面） |
| 隔离清单 | `selftest_v2.mjs:690-706` | 自测会一并隔离 `MCHAT_MAILBOX_DIR` / `MCHAT_TASKS_DIR` / `MCHAT_THREAD_LOCKS` / `MCHAT_DATA`，否则会写进真实 `outputs/dialog`、`docs/tasks`、真实锁目录 |

**判据**：桩程序走**退出码 + 文件落盘**两路信号 → 正好能同时钉住"退出码 0 不算唤醒"与"mtime 不算唤醒"这两条反面实证。

## 七、我不动的（红线照旧）

- 不进 `D:\agent_crew_kits`（套件仓归 `codex-套件`，要它先同意）；
- 不改 `board.mjs` / `crew_host.py` / `server.mjs`（含别人的仓与共享文件；本清单只是证据）；
- 不抢写锁、不改 `spec/`、不起常驻进程、不跑 `remote-control start` / `app-server daemon`。
