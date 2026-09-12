# 桥的替代方案（2026-09-11，`codex-总监` 落单）

> 背景：桥（`deepseek-harness-mcp-bridge`）因**平台缺陷**（deferred 命名空间重复不去重）把元老线锁死，见 `docs/tasks/PLT-001.md`。老板指示：**无风险拆掉、把替代方案跑起来**。

## 一、桥现在的状态（三件套）

| 部位 | 处置 | 可否回滚 |
| --- | --- | --- |
| **Codex 侧 MCP 注册**（`~/.codex/config.toml`） | **已注释**（`scripts/plt001_stop_bleed.py`），`codex mcp list` 只剩 `cua_repl`/`node_repl` | ✅ `--revert` 一条命令；备份 `config.toml.bak-20260911-062505` |
| **WSL 里的桥本体**（`/home/lgy/.dsh-bridge`，95 依赖 + `server.mjs`） | **原样保留、不删**：① 便于快速恢复 ② **Hub 还在读它的信箱目录** ③ 遵"废弃只标记" | ✅ 未动 |
| **附属补丁脚本** `tools/mobile_chat/patch_bridge_progress*.mjs` | **标记废弃**（不删） | — |

## 二、桥原本提供什么 → 现在用什么替代

| 能力 | 原实现 | 替代 | 状态 |
| --- | --- | --- | --- |
| **Codex → DSH 发信/派活** | 桥的 MCP 工具 | **看板 `@dsh-老员工` → Hub 转投它的信箱 → 它上场自读** | ✅ **已在跑**（今晚全程用的就是它） |
| **DSH → Codex 发信** | 桥信箱 | 写 `outputs/dialog/pending_<slug>.ndjson`（它在 WSL 可写 `/mnt/e/...`）或 `POST /api/mail` | ✅ 可用 |
| **DSH → 唤醒 Codex 线** | 桥的反向通道（`approval-policy: never`） | **不用**——那正是危险通道（无人审批执行），我们不要 | ❌ 弃用 |
| **Hub 展示桥信箱** | 读 `\wsl.localhost\...\.dsh-codex-bridge\{messages,tasks}` | **保持不变**（Hub 继续读；读不到只是少一路来源，**降级安全**） | ✅ 保留 |

## 三、正式通道（替代桥之后的"标准姿势"）

1. **定向投递**：`outputs/dialog/pending_<slug>.ndjson`（或 `POST /api/mail`）——**投递可靠、不保证唤醒**（I3：投递与唤醒分离）；
2. **广播**：`docs/COMMS_BOARD.md`（走 `POST /api/post`，**带自己的看板名**）；
3. **唤醒**：DSH 侧可用（Web RPC `session/prompt`）；**Codex 侧当前无**（归 `HUB-005`）；
4. **兜底**：值守分线只读代答 + 手机状态栏「信箱 N」可见化。

## 四、红线（恢复桥的前提）

**不许擅自恢复桥的 MCP 注册。** 要恢复，必须同时满足：

1. 老板点头；
2. 先给桥加 **`omit_tools_from: ["code_mode","deferred"]`** 豁免（否则它还是一颗 deferred 雷）；
3. 先确认那条 **`approval-policy: never` 反向通道已加闸**（否则等于给"无人审批执行"开了口）；
4. 登记（谁改/改了什么/**影响面=所有线**）+ 回滚点 + 风险说明（见 `AGENTS.md` 红线、`LESSONS.md` L2）。
