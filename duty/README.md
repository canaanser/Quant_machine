# duty/ — 值守子系统(基础设施, 2026-09-09 定稿 → 2026-09-09 晚改为常驻型)
主值守 = **duty_engine.py**("装任务插件的值班人员"), **常驻进程(stockdb式)**: 登录自启后 24h 不退出,
交易时段干活、盘后空转待命; 不再"每日拉起/收盘退岗"。watch_all.py(v2)退役备用。
单实例锁 `outputs/resident.lock` 防双跑(进程崩溃OS自动放锁)。

## 架构(老板定的分层)
duty(调度/值守) → 根 self_api.py(对外冻结接口) → core(内核)。只调 API, 不绕内核。

## 六块
1. 心跳调度循环(tick 1s, 心跳文件每秒刷新)
2. 任务注册表: name -> {fn, freq_sec | window | at_time(定点), once}
3. 出勤表 = duty/schedule.yaml(market/session/tasks 可改, 改完重启生效)
4. 交易时段状态机: 盘前/待开/上午盘/午休/下午盘/尾盘窗/收盘/盘后/周末
5. 盯市: 盘中 60s 拉持仓实时价, 距防崩3%内预警留痕(任务 monitor)
6. 状态持久化 + 幂等(once 任务当日只跑一次) + 决策留痕 duty_decisions.log

## 任务
| 任务 | 节奏 | 干什么 |
|---|---|---|
| heartbeat | 20s(循环本身1s) | 心跳文件 |
| monitor | 60s 窗口9:30-11:30,13:00-14:40 | 持仓实时价/逼近防崩预警 |
| tail_exec | 14:44 定点 once | 卖触发(防崩/峰顶/滞涨)自动放单; 读 next_plan.csv 自动放买(当日防重) |
| close_sync | 15:05 定点 once | 回账 sync_fills |

## 执行细节(防错要点)
- 取价覆盖 **持仓 + next_plan 买码**(只取持仓价会漏新买 — 曾犯)
- 14:44 取价失败 -> 当日不动作(防误单)
- 单实例锁: 登录自启任务 与 看门狗(每5分钟心跳过期即拉) 双拉只活一个; 崩溃OS自动放锁
- 常驻模式永不自动退岗; 跨日自愈: 零点自动清 once 状态(次日14:44可重触发)
- 心跳每 tick 刷新 -> 进程死掉 8 分钟内看门狗拉起 duty_engine

## 用法(Windows cmd 权威)
解释器 = **E:\python\量化看守.exe**(= pythonw.exe 的改名副本, 只为让任务管理器进程名显示"量化看守";
本质仍是解释器, 改 duty_engine.py 照常生效; Python 重装后需重建副本:
`copy E:\python\pythonw.exe E:\python\量化看守.exe`)
```
E:\python\量化看守.exe -B duty\duty_engine.py --selftest   # 一回合自检
E:\python\量化看守.exe -B duty\duty_engine.py --shadow     # 观摩: 只演练+留痕不放真单(心跳写独立文件)
E:\python\量化看守.exe -B duty\duty_engine.py              # 常驻(默认, stockdb式, 24h不退)
E:\python\量化看守.exe -B duty\duty_engine.py --retire     # 一次性: 收盘15:45自动退岗(一般不用于生产)
```
计划任务(tools/create_watch_tasks.bat, GBK编码, 双击即可重建):
- QuantDutyOnLogon 登录时 -> 量化看守.exe duty_engine.py(常驻, 24h 在任务管理器可见)
- QuantTrayOnLogon 登录时 -> 量化看守.exe tray_guard.py(系统托盘壳, 状态栏图标+右键菜单)
- QuantWatchDog    每5分钟全天 -> 量化看守.exe watch_all_dog.py(心跳过期>8min拉起引擎, 兜底)

托盘壳 tray_guard.py(状态栏): 图标颜色 绿=引擎在岗/黄=心跳过期/红=离线;
右键菜单: 状态/时段/心跳, 启动值守引擎, 重启值守引擎, 打开值守日志, 打开outputs目录, 退出壳。
托盘只操控/看护, 绝不代下单(真实买卖仍只有引擎14:44执行段做)。

手动停/起:
```
taskkill /PID <引擎PID> /F                      # 停常驻引擎
E:\python\量化看守.exe -B duty\duty_engine.py   # 手动再拉起
taskkill /PID <托盘PID> /F                      # 停托盘(引擎不受影响)
E:\python\量化看守.exe -B duty\tray_guard.py    # 手动再拉起托盘
```

## 出勤表示例(duty/schedule.yaml)
- market.off_days: 例 ["2026-10-01"] 休市日停跑
- tasks.monitor.window / tasks.*.at_time / tasks.*.enabled 均可改

## 未来
做T模块 = 注册 cadence='1m' 的任务(需底仓/日T额度字段预留), 复用 self_api.dispatch。
