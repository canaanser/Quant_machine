# 给 Codex: watch_bridge 等调度/桥交接说明

> 老板 2026-09-10 分配: 调度治理(watch_bridge/唤醒/消息桥)归 Codex 管理; DSH 不再自管桥。
> 本文件为 Codex 接管用的事实清单(DSH 侧不再动这些)。

## 一、现在机器上有什么(与对话无关、一直在跑)
- 值守引擎: `E:\python\量化看守.exe -B duty\duty_engine.py`(Windows 计划任务 QuantDutyOnLogon 登录自启;常驻, 心跳写 outputs/watch_heartbeat.txt)
- 托盘: `...tray_guard.py`(QuantTrayOnLogon); 看门狗 QuantWatchDog 每5分钟; 数据同步 QuantDataSync 20:00(run_data_sync.py, 10分钟后关 exe 定稿); QuantDailyScan 20:15; QuantDailyPlan 20:40。
- 以上是 Windows 计划任务, 与任何对话/会话无关, 一直在。 **不要重复拉起引擎**。

## 二、watch_bridge 是什么(当前归你管)
- 文件: `scripts/watch_bridge.py`(DSH 曾以"会话后台job"托管)。
- 作用: 常驻低耗, 在交易时点(09:20/10:00/10:30/11:15/11:30/13:10/14:00/14:30/14:44/15:08)、引擎心跳断>150s、或 outputs/inbox 出现未处理 *.json task 时退出 —— 退出即"叫醒 DSH"。
- ⚠️ **它是按"由某会话作为后台 job 启动"才能把退出通知推给 DSH**。若以普通进程跑, 只执行不通知。Codex 接管后请按此维护(需叫醒 DSH 时用会话 job 方式跑它; 或改用你自己设计的中控)。
- 注意: 若 DSH 换了会话, 旧 job 归属失效, 需要在新会话侧由 Codex/DSH 重新托管才有通知效果——具体由你设计。

## 三、消息桥(inbox)约定(照 AGENT_SPLIT.md §3)
- `outputs/inbox/` 投任务(`*.task.json`: to/do/target/why/accept), `inbox/done/` 归档, `inbox/reports/` 回报。
- 任何一方(Codex/DSH)发现未处理 task 即处理。

## 四、给 DSH 的交接提示
- DSH 职责收缩为: 双线执行/研究/盯盘/复盘/写代码(快); 不碰 git(老板令: 一律不动); 不管桥与调度。
- DSH 侧通讯: Codex 若需要 DSH 干活, 投 inbox task → 桥/Codex 调度唤醒 DSH; DSH 回报写 reports。
