# PLT-007 实现说明：事件注入 / 通道层（DSH 门铃工具）

- 卡号：`PLT-007`｜执行：`codex-唤醒通道`（lead）｜验收人：`codex-量化总监`
- 交付物：`tools/mobile_chat/dsh_doorbell.mjs`（实现）+ `tools/mobile_chat/selftest_doorbell.mjs`（自测）

## 一、做了什么

把"线 → DSH"的机器叫醒固化成**仓库内、Windows 侧、零依赖**的工具：

```
node tools/mobile_chat/dsh_doorbell.mjs --file <正文文件> [--session <会话id>] [--dry] [--list]
```

它做四件事：① 读正文文件（正文不拼进命令行）；② `POST /api/session/prompt` 注入；③ **验证对方真起了回合**（`session/list` 的 `updatedAt` 变化，30 秒窗口）；④ 把结果与用量记账（`outputs/dialog/doorbell_state.json`）。

守卫（卡面验收②）：

| 守卫 | 实现 |
|---|---|
| requestId 一信一号 | 每次注入新 `requestId`（uuid） |
| 同内容不重发 | 正文 hash 记账，10 分钟内同内容跳过（`--force` 可强制） |
| 401 自动重换 cookie | 读启动日志 token → `GET /?token=` → 写回 cookie → **间隔 ≥2s** 重试一次 |
| 日限流 | 默认 20/天，**按本地日期**（不用 UTC，避免跨日记错） |
| 失败兜底 | 回投 `outputs/dialog/pending_dsh-main.ndjson` + 打印告警；`--alert-board` 才上板 |
| 验收判据 | 只看投递成功**不算过**，必须 `updatedAt` 变化 |

## 二、两道边界（`codex-总监` 06:52 裁定，必写）

1. **与相邻卡的边界**：
   - `PLT-002`（`scripts/crew_host.py`：沙箱外小工宿主——镜像/门铃/账本/自动合入/自我重载）：本工具**不碰** crew_host，也**不改**它的任何调用点；它是"**给 DSH 的那条腿**"，crew_host 管的是"各 Codex 线的门铃"。
   - `PLT-005`（能力门禁）、`PLT-006`（裁决阶梯与老板面门槛）：本工具**不做**权限判定、不做要不要叫醒的判断——**谁决定叫，谁调用它**；它只负责"叫得响且可验证"。
   - **不改** `crew_host.py`，**不改** `pushed.ndjson` 账本口径；本工具自己的记账在 `outputs/dialog/doorbell_state.json`（与那份账本**不是一回事**，互不覆盖）。
2. **真删/停平台件**：`DSH-Board-Sentinel`（计划任务）不在本卡范围；本卡**不动计划任务、不动服务注册**。

## 三、本次踩到并修掉的两个本机坑（写下来免得复演）

1. **环境死代理**：机器上挂着已死的 `http_proxy=127.0.0.1:7890`，**Node 的 fetch 会照用** → 请求挂死到超时（`This operation was aborted`）。工具启动即摘掉 `*_proxy` 变量（Python 侧 AR-001 早已这么绕，Node 侧这次补上）。
2. **`process.exit()` teardown 崩溃**：直接 `process.exit(code)` 在 Windows/Node 上会以 `0xC0000409` 退出（明明逻辑已经跑完）。改成设 `process.exitCode` 自然退出。

## 四、自测（可复跑）

```
node tools/mobile_chat/selftest_doorbell.mjs
```

桩服务顶替 dsh web，9 条用例：成功并验证到回合 / 同内容不重发 / `--force` / 日限流 / 401 重换 cookie 并重试 / 重试间隔 ≥2s / 失败兜底回投 / 缺 `--file` 拒发 / `--dry` 不真发。
**结果：9/9 通过**（临时目录留证，脚本会打印路径）。

## 五、真实链路证据（不是桩）

2026-09-13 06:53:27 用同一份 payload 手工对着真 `dsh web` 注入 `dsh-老员工`：`accepted`，且该会话 **06:53 起了回合**（`updatedAt` 变化、turns=1885，此前最近活动 01:09）——**满足"真起了回合"的验收判据**。

## 六、未结

- 工具尚未在**真端点**上跑过一次完整调用（上面那条是同一 payload 的手工投递）；要跑请给一句"可以叫一次"，我就用它真发一条（会消耗 dsh 一个回合）。
- 合 `main` 不归本卡：过门禁转 `codex-总监`。
