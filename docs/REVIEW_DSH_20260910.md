# 代码审阅单：DSH 2026-09-10 变更（Codex 主审）

审阅人：Codex（主审阅） 日期：2026-09-10 16:1x
范围：dsh 当日未提交变更（git 未动）

- `duty/duty_engine.py`（+52 行：board_relay、`t["last"]`）
- `duty/schedule.yaml`（board_relay 配置）
- `scripts/net_guard.py`（新增，8101B）、`tools/register_net_guard.ps1`（新增）
- `scripts/board_listener.py`（新增）、`scripts/build_acct2.py`（新增）
- `docs/STATE_ANCHOR.md`（更新）、`docs/HANDOVER_20260910.md`、`docs/ONBOARD_GUIDE.md`、`docs/BRIDGE_NOTES_DSH.md`、`outputs/inbox/reports/dsh_20260910_incident.md`

## 一、结论

**有条件不通过，暂不合入 main。**

- 事故复盘（根因＝进程链启动上下文被限网）与现场处置（计划任务重拉）已核验属实，认可。
- 新增代码存在 2 个 P0：**双看板派单重复**、**net_guard 盘中误杀风险**；另有 3 个 P1。
- `net_guard` 可按「过渡期只告警 + 执行窗口保护」继续启用；`build_acct2.py` 修复前只允许 `--dry`。

## 二、P0（必须先修）

### P0-1 双看板派单，同一行会投两次
- 位置：`duty/duty_engine.py:223-266`（board_relay，freq 20s） vs `tools/mobile_chat/board.mjs:278`（queueDshFromBoard）/`:310-330`（checkTimeline）
- 事实证据：今日 inbox 同时出现两套文件——`board_relay_20260910_065437/065757/071817`（引擎投）与 `board_dsh_20260910_065428/071809`（Codex 服务投），同一条 @dsh 留言被投递两遍。
- 风险：dsh 重复处理/重复回写看板；两套行游标（`board_relay_state.json:seen` 与 board.mjs 的 `boardOffset`）不同步，漏投/重投都会出现。
- 要求：**同类事件只保留一个投递方**（建议保留 Codex 侧服务、删除引擎 board_relay，理由：调度治理归 Codex；引擎专注交易），删除后同步清理 `outputs/board_relay_state.json` 与 schedule.yaml 配置项。

### P0-2 net_guard 盘中误杀风险
- 位置：`scripts/net_guard.py:35-40`（判定阈值）、`:70-76`（交易窗口 9:25-11:35/12:55-14:50）、`:129-160`（杀进程+重拉）、`:198-205`（判定分支）
- 风险：判定条件为「探针通 + 近 12 分钟 ≥4 条失败」；一次行情源抖动/单票异常即产生 4 条重试日志 → 触发**盘中强杀引擎并重拉**；窗口包含 14:40-14:50 执行段，正是最不能重启的时候；无「有在途委托不得重启」保护，存在重复下单/漏跟单风险。
- 要求：
  1. 执行窗口（14:35-15:05）以及引擎「执行段进行中」时，只告警不重启；
  2. 需连续两个检查周期（≈6 分钟）均满足条件才触发重启；
  3. 重启前检查当日 `orders_sent`/`execution_report` 是否存在在途委托；
  4. 保留「无价不动作」底线不变。
- 过渡要求：未修好前，`net_guard` 默认改为只写告警（不自动重启）。

## 三、P1（合入前必须处理）

### P1-3 计划任务注册方式不可靠
- 位置：`tools/register_net_guard.ps1:6,9`
- 问题：`schtasks /create` 未指定 `/ru`、`/rl`，任务只在**当前用户登录会话**下运行（用户登出/无人登录即失效，与"安全网常驻"表述不符）；`Get-ChildItem E:\python\*.exe` 排除 `python*` 后可能返回多条路径，`/tr` 会被拼坏；未提供卸载方式。
- 要求：显式写死 exe 路径；文档注明"依赖登录会话"；脚本支持 `-Remove` 注销；可在注释中写明失效条件。

### P1-4 board_relay 实现健壮性（若保留）
- 位置：`duty/duty_engine.py:233-266`
- 问题：行数游标（`seen`）在文件被裁剪/头部编辑后错位；过滤条件 `"@dsh" in ln and "DSH：" not in ln` 过宽，历史引用行、`@DSH` 大小写、含 `@dsh` 的 Codex 回复都可能误判；同秒多行会因文件名秒级时间戳而互相覆盖；20s 全文件读取随看板增长成本上升。
- 要求：改为行首格式匹配（`^- @dsh\b`）＋作者过滤；或按 P0-1 结论直接删除。

### P1-5 board_listener.py 机制无效且路径错误
- 位置：`scripts/board_listener.py`（全文件）
- 问题：依赖「会话 job 退出→平台唤醒 DSH」，dsh 已实测会话 job 回合结束即被回收（job_list 为空），机制不成立；且硬编码 `E:\...` 路径，在 WSL 侧不可达。
- 要求：标记弃用并删除，避免后人误以为存在常驻监听。

## 四、P2（可随修）

### P2-6 build_acct2.py 生产化缺口（修复前只允许 --dry）
- 位置：`scripts/build_acct2.py:17-20,34-46,57,74-94`
- 问题：① batch2 未按 batch1 的实际成交差额计算，skips/部分成交会超买或漏买；② `lots` 未保证 100 整数倍；③ 限价 `现价*1.002` 未受涨停价约束，可能废单；④ 无按 `date+batch` 防重，重复 `--send` 会重复放单；⑤ 无金额上限校验；⑥ `prev_close` 对 `rdx.day_rows` 无异常兜底；⑦ 日志只记 sids 数量，无 code→sid 映射。
- 要求：加防重、整手校验、涨停上限、单笔/当批金额上限、成交差额核对；先只在 `--dry` 下使用。

### P2-7 `t["last"]` 修复正确，但属行为变更，需回归
- 位置：`duty/duty_engine.py:206`
- 说明：HEAD 版 `last=0` 从未更新，导致 freq 门限失效（周期任务退化为每 tick 触发，decisions 日志膨胀到 3MB 级）；本次补上更新是正确的修复。
- 要求：回归确认 heartbeat=20s、monitor=60s、board_relay=20s 的真实触发间隔；注释说明该字段语义，避免后人误删。

### P2-8 运行态文件与文档
- `outputs/board_relay_state.json`、`outputs/inbox/` 属运行态产物，保持 untracked 或纳入 .gitignore 口径；
- `docs/STATE_ANCHOR.md` 事故记录准确，建议补一条「计划顺延规则」（9/11 未执行的 9/10 计划如何处理）；
- `FILE_INVENTORY.md` 增补今日新增文件（net_guard/board_listener/build_acct2/BRIDGE_NOTES 等）。

## 五、验收清单（复审用）

1. 看板 `@dsh` 只产生一种 task 文件（唯一机制，无重复投递）。
2. net_guard 三个场景实测：单周期失败→只告警；连续两周期失败→重启；14:35 后→不重启。
3. 注册脚本可注册/可注销；任务在登录会话下自动运行。
4. `build_acct2.py --dry` 输出与 plan2 一致；`--send` 有防重与整手/涨停/金额校验。
5. duty_engine selftest 通过；freq 间隔回归符合配置。

## 六、认可项

- 事故根因定位与证据链（两种上下文探针对比、父进程已死、写盘正常/仅 socket 被拒）成立；
- 15:44-15:46 现场处置有效（新引擎 pid 24524 父进程=计划任务宿主，心跳正常），Codex 已独立核验；
- HANDOVER 四、五、六节内容可作为 4 项引擎内建修复的输入（自检+net 心跳标记、托盘双条件、取价失败告警、禁止沙箱启动值守）。
