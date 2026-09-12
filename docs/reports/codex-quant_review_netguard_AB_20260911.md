# 独立复核意见：net_guard 判据 A/B（codex-量化总监）

> 性质：**独立复核意见**，不是批文。批文归 `codex-总监` 2026-09-11 02:26（那一版已批）；本文件只写我核过什么、结论、遗留。

## 核过的内容

- `_target_pids()`（匹配 tray_guard + duty_engine，用于终结）与 `_engine_pids()`（只匹配 duty_engine，用于成功判据）已分离（`EXE_PAT` / `EXE_PAT_ENGINE`）。
- `heartbeat_content_ts()`：取心跳文件最后一行的行首 `YYYY-MM-DD HH:MM:SS` 转 epoch；解析失败退回 `heartbeat_mtime()`。
- `_wait_restart_verified()`：要求 **旧引擎 PID 全消失 + 出现新 duty_engine PID + 心跳内容时间戳前进** 三条同时成立；窗口 30–120s 轮询。
- `restart_engine()`：拿不到旧引擎 PID（查询失败或确实没有）一律中止；`/end` 失败仅告警、`/run` 失败即中止告警；`mark_success()` 只在成功路径写 `last_success_ts`。
- 证据来源：代码逐段阅读 + dsh 02:20/03:15 信箱回执（判据单测 A/B/C/D、受控复验 82s 通过）。

## 结论

判据实现与"只认引擎 + 心跳内容前进 + 失败不报成功"的要求一致，**无异议**；不改动任何代码。

## 遗留 / 风险（供 owner 决策，不阻塞）

1. 心跳判据依赖行首时间戳格式；写入方若改格式会静默退回 mtime（较弱判据）。建议格式变更时同步本脚本。
2. `_query_pids()` 用正则从 PowerShell stdout 抓数字；若 PowerShell 报错文本含数字，理论上可能误读。建议改为结构化输出或校验返回码。
3. `/end` 失败只告警继续 `/run`；若旧实例仍被任务框架认为"运行中"，`/run` 可能失败——已被返回码与告警覆盖，但会走失败路径（不误报成功）。
