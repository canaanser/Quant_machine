# AR-003 审阅：net_guard 自动重启判据收紧（A/B）

- 日期：2026-09-11 03:1x
- 审阅：codex-量化总监
- 范围：`scripts/net_guard.py::restart_engine()` 与三道护栏
- 结论：**通过，允许保持武装（--enable-restart）。**

## 一、判据（本次收紧后）

1. 重启前：抓取旧 `duty_engine` PID；为空即 ERROR + 看板并中止（不删 lock、不 /run）。
2. 重启后成功需三项同时满足：
   - 旧 `duty_engine` PID 全部消失；
   - 出现新的 **duty_engine** PID（托盘 PID 不计入校验）；
   - 心跳**内容**行首时间戳严格前进（不可解析才退回 mtime）。
3. 校验窗：min 30s / max 120s / 5s 轮询；窗口结束未满足 → ERROR + 看板告警并中止本轮，
   `mark_success()` 只在成功路径写 `last_success_ts`。
4. 护栏未动：14:35–15:05 执行窗、在途委托门禁、连续两周期 + 20 分钟冷却。

## 二、验证证据

- `py_compile` OK；`--selftest` ALL PASS。
- 判据单测：A 旧引擎仍在=False / B 托盘起来但无引擎=False /
  C 新引擎但心跳内容未前进=False / D 三条齐=True。
- 非交易时段受控复验：03:13:25 终止旧引擎 24924 → 03:14:46 判成功，
  新引擎 32056，心跳内容前进，耗时约 82s；现役心跳
  `2026-09-11 03:15:13 state=duty|盘前|tasks=4`。
- 运行模式：日志显示 `mode=auto-restart`，武装已生效。

## 三、遗留与条件

- 若盘中出现“冷启 >120s”的误报失败，把 max 放宽到 150s，不改其余判据。
- 任何护栏被临时改动（测试需要）必须先退回 alert-only，复测后再武装。
- 本条为 infra 改动，不涉及下单/资金参数；后继若合入 `main`，按本记录验收。
