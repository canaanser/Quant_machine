# TRD-003 审阅记录：卖单元组 4→5（`tail_exec`）

- 审阅对象：`duty/duty_engine.py`（`task_tail_exec()`，3 行改动）｜分支 `feature/trd-003-tail-exec-fix`
- 审阅人：`codex-量化总监`（改方）｜**独立验收：门禁 + `codex-总监` 合入**
- 日期：2026-09-13 07:0x

## 一、审阅结论

**修法正确、面最小**：只把卖单构造对齐 `self_api.dispatch()` 的 5 元组契约，并把同码去重从 `s[0]` 改到 `s[1]`；
不触碰买入路径、不改限价口径、不动护栏与计划文件格式。

## 二、证据链

1. 事故原文：`outputs/inbox/reports/dsh_20260911_a1_exec_incident.md`（14:44 抛错、14:46 人工接管 5 笔）；
2. 契约真源：`self_api.py` `def dispatch(actions)` 文档串 `执行一组 (action,code,shares,px,name)`，解包 `(a,c,s,p,n)`；
3. 语法：`py_compile` OK；
4. **回归测试**：`scripts/test_duty_tail_exec.py` → ALL PASS（含"4 元组必崩"的反向断言，直接复刻 9/11 事故）。

## 三、风险与边界

- **未生效风险（最大）**：现役引擎进程跑的还是旧代码，**不在 14:44 前重启就等于没修** → 已列为未结第 1 条，报平台 owner 决定重启时机；
- 该测试用桩 `_br`，不碰真单；不写 `C:\emq` 任何文件；
- 若 `plan` 里出现非 `sell/buy` 的旁路值，行为与改前一致（不新增分支）。

## 四、遗留

1. 重启时机（平台面）→ `codex-总监`；
2. 合 `main` → 门禁 + `codex-总监`；
3. 同源风险扫描：`duty/` 下是否还有别处构造"卖单/买单"给 `dispatch`（本次只扫了 `tail_exec`）→ 建议纳入 `dsh-老员工` 的 `TRD-002` 巡检。
