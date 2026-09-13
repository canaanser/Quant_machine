# 全局规约指针页 · 平台级改动登记（L2 四件套）

> 老板 2026-09-13 08:5x 批准：「让班组规约变成**任何工作目录都加载得到**」。三步照做：先实测 → 按结果走 → 齐三件。

**结论（头 5 行）**

1. 在 `C:\Users\Administrator\.codex\AGENTS.md` 放了一页**指针页**（230 字节）：只写"规约真源 = `E:\stockgate\Quant_Alpha_System\AGENTS.md`，开工先读它"。
2. **实测有效**（不是推断）：`D:\agent_crew_kits` 与 `D:\a股数据` 各起一条一次性会话，**两条都 `LOADED`**，且回引的次行**逐字**等于指针页首行。
3. 归属由**会话账本自己记的 `cwd`** 判定，不靠运行顺序推断（thread → cwd 见 §二）。
4. 判据（可复跑）：`node .private/codex-director/check_probe.mjs`，退出码 0 = 成立。
5. 因为有效 → 指针页**留着**；备选路线（搬 `AGENTS.md` + `crew_rebirth.mjs` + `evidence.mjs` 去 D 盘）**未启用**。

## 一、改了什么（逐字）

文件 = `C:\Users\Administrator\.codex\AGENTS.md`｜230 字节｜sha256 `F9B7A31BE4A3F15ED17568785CED670B73F7E21FDC774D1CE131B0D83562C897`

```
# 规约真源（指针页）

规约真源 = `E:\stockgate\Quant_Alpha_System\AGENTS.md`

开工先读它。

本页只是一枚**指针**：正文只在 E 盘那一份，别在这里写第二份（一处事实只写一处）。
```

**正文仍只在 E 盘一份**——守「一处事实只写一处」：以后改规约**不用动这页**。

## 二、实测证据（老板第 1 步：先实测，不许猜）

| 会话 thread | 账本自己记的 cwd | 它自答首行 | 自答次行 | 日志 |
| --- | --- | --- | --- | --- |
| `01a09848-46b1-74a1-a62a-c604cc555be6` | `D:\agent_crew_kits` | LOADED | `# 规约真源（指针页）` | `outputs/logs/probe_global_agents_2026-09-1309012.log` |
| `01a09848-a6a2-7521-a5eb-63f44202f629` | `D:\a股数据` | LOADED | `# 规约真源（指针页）` | `outputs/logs/probe_global_agents_2026-09-1309014.log` |

**记一笔自己踩的坑**：第一次实测在沙箱里**会话根本没起起来**（它写不了自身状态库 → `readonly database` / `os error 5`），
脚本据此报了"没加载到"——那是**假结论**；提权重跑才算数。（判据必须能区分"没加载"和"没跑起来"。）

## 三、L2 四件套

| 项 | 内容 |
| --- | --- |
| **谁 / 改了什么** | `codex-总监`（工号 `codex-director`）：新增全局指针页 `C:\Users\Administrator\.codex\AGENTS.md`，**只含指针、不含正文** |
| **影响面** | **所有线**：每个会话启动都会多加载这一页（约 230 字节），并因此知道规约真源在哪 |
| **回滚点** | **删掉该文件即回退**（无状态、不需要备份；正文与本仓一字未动） |
| **风险** | ① 指针与真源不同步 → 本页不含正文，改规约无需动它；② **加载了指针 ≠ 真读了真源** → 靠 `whoami`／门铃／派活链路兜底；③ `~/.codex/AGENTS.md` 是**本机实测有效、非官方契约**，平台升级后可能失效 → 失效即走老板给的备选；④ 写错字 → 有 sha256 登记 + 可复算核法 |

## 四、核于

- 核于 09:02｜核法 `node .private/codex-director/check_pointer.mjs`｜结果 **PASS**（sha256 与登记一致、含真源路径与「开工先读它」）
- 核于 09:02｜核法 `node .private/codex-director/check_probe.mjs`｜结果 **PASS**（两个工作目录，cwd 由账本证）
