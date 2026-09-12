# 看板哨兵（DSH Board Sentinel）— 规格与运维

> 目标：**老板在看板写一行 `- @dsh …`，DSH 会话自动被叫醒并回写看板。** 其它事件一律不触发。
> 归属：AR-001（Codex）。落地：2026-09-10 19:41。

## 一、触发规则（窄是刻意的）

看板名规约见 `docs/BOARD_NAMES.md`（`前缀-对话框名`）。本哨兵认这三个行首句柄，且**署名必须是你本人**：

```regex
^- (@dsh-老员工|@dsh-main|@dsh) \d{4}-\d{2}-\d{2} \d{2}:\d{2} 老板[：:]
```

- `@dsh-老员工` 是**主句柄**（对话框「老员工」= dsh 值守主会话）；`@dsh`、`@dsh-main` 是兼容旧写法。
- `@dsh-quant`（仓库执行实例）与 `@codex-*` 一律**不**触发本会话唤醒。句柄是**整词匹配**，所以 `@dsh-quant` 不会因为前缀与 `@dsh` 相似而被误伤。

为什么必须这么窄——看板今晚的真实数字（101 行时统计）：

| 匹配方式 | 命中行数 | 后果 |
|---|---|---|
| 任意位置含 `@dsh` | 23 | 文件头说明 + 别人转述你的话都会误触发 |
| 行首 `- @dsh ` | 8 | 仍包含 Codex/DSH 自己发的行 |
| 行首 `- @dsh ` **且署名 `老板：`** | **7** | 真实的"老板 @ 他"，零误报 |

（上表是 19:41 首次落地时按当时口径统计的；20:0x 起句柄扩到 `@dsh` / `@dsh-main` 两个——老板 19:46 实际用 `@dsh-main` 测试过，当时规则没覆盖，那条没触发。）

署名不是 `老板` 的 `- @dsh` 行会被写进日志（`SKIP`）但不投递。联调时可临时 `--author Codex` 覆盖。

## 二、不重放历史的保证

看板是只增不删的日志，历史 `@dsh` 行永远在文件里。哨兵的状态放在**仓库外**：

```
C:\Users\Administrator\.dsh-sentinel\
  state.json     # 已读指针（行号 + 该行内容哈希）
  cookie.txt     # 门铃 cookie（0600 级，绝不出仓）
  sentinel.log   # 逐轮留痕
```

三条硬规则：

1. **冷启动只记不发**：没有 state.json 时，把当前尾部记为已读，一条都不投。
2. **锚点校验**：每轮先确认"已读指针前一行"的内容哈希没变；变了（文件被重写/截断）就按内容重找锚点，找不到就基线到末尾——**任何情况下都不回头重放**。
3. **每轮最多叫醒一次**：同一轮里出现多条 `@dsh`，只投第一条，其余留给下一轮（1 分钟后）。

## 三、投递路径

调用 AR-001 打通的 Web RPC（协议见 `docs/reports/AR-001_arch.md` §二）：

`POST http://127.0.0.1:3080/api/session/prompt`，`method="session/prompt"`，参数名 `request`。

- 唤醒词 = 你的**原文**（另加一行处理要求），不重写、不概括。
- cookie 从 `C:\Users\Administrator\.dsh-sentinel\cookie.txt` 读；**收到 401 就自动重换**（token 每次 `dsh web` 重启轮换）。
- 取 token 时读 `\\wsl.localhost\Ubuntu-24.04\home\lgy\.dsh-web.log`；**只在需要换 cookie 时才读**，没事不碰 WSL。

## 四、节流与上限

| 闸门 | 值 | 说明 |
|---|---|---|
| 每轮投递数 | 1 | 多条 @ 留到下一轮 |
| 每日上限 | 20 | 命中上限后**不丢行**，顺延到次日继续 |
| 运行频率 | 1 分钟 | 计划任务触发，无事件时只读一次看板就退出 |
| 单次运行上限 | 5 分钟 | 超时被计划任务掐掉，不会挂死 |

## 五、失败兜底

- 投递失败（端口不通 / 401 换 cookie 后仍失败 / 任何异常）→ 写一条
  `outputs/inbox/dsh_wake_failed_<时间戳>.task.json`（带原文与原因），并写 `sentinel.log`。
- 哨兵自身掉线：每轮会检查"上次运行时间"，超过 10 分钟就记 `WARN 哨兵掉过线`。
- **已知缺口**：如果 Windows 计划任务整个停摆，没有任何外部机制会告警——这条仍需人（或把告警挂到别处）。决策书里的兜底"退回投 `outputs/inbox/` + 看板 `@老板`"目前只做了上半句。

## 六、部署与开关

```powershell
# 看状态
& 'E:\python\python.exe' E:\stockgate\Quant_Alpha_System\tools\mobile_chat\dsh_board_sentinel.py --status

# 干跑（只报不发，会推进已读指针）
& 'E:\python\python.exe' ...\dsh_board_sentinel.py --dry-run

# 真跑一轮（正常情况下由计划任务每分钟自动跑，不需要手动）
& 'E:\python\python.exe' ...\dsh_board_sentinel.py

# 基线对齐（把当前尾部记为已读，不触发）
& 'E:\python\python.exe' ...\dsh_board_sentinel.py --init

# 停用 / 启用
Disable-ScheduledTask -TaskName 'DSH-Board-Sentinel'
Enable-ScheduledTask  -TaskName 'DSH-Board-Sentinel'
Unregister-ScheduledTask -TaskName 'DSH-Board-Sentinel'   # 撤掉
```

计划任务：`DSH-Board-Sentinel`，**每分钟一次、短跑即退（无常驻进程）**，因此不占用端口、不构成常驻进程、不触碰 9/10 那次"沙箱上下文拉常驻进程被限网"的坑。

**必须用 `pythonw.exe` 启动**（不是 `python.exe`）：否则每分钟会弹一个一瞬间消失的控制台窗口。`pythonw` 下 `sys.stdout is None`，脚本已把它接到 `sentinel.log`，CLI 输出不丢。

## 七、成本

- 哨兵本身 **0 token**（脚本不是模型）。
- 每次真正叫醒 = 一个会话回合。实测（AR-001 §3.3）：**一次唤醒的输入 ≈ 该会话上下文规模**（主会话 219 k），若被叫醒后要跑多步工具，还会 ×步数。
- 所以闸门比"省钱"更重要的是"**别误触发**"——这也是第一节把规则收窄到"署名你本人"的原因。

## 八、边界（做不了 / 故意的）

- 只覆盖**看板 `@dsh`**。心跳断 / 20:00 同步完成 / 14:44 执行结果这些事件**不触发**（老板 2026-09-10 决定先只做 @，跑稳再扩）。
- 不读会话列表、不解析会话状态、不碰资金与下单。
- `dsh web` 进程或 3080 端口不在时，门铃失效 → 走第五节兜底。

## 九、变更记录

| 时间 | 变更 |
|---|---|
| 2026-09-10 19:41 | 首次落地：触发句柄 `@dsh`，署名 `老板`，计划任务每分钟一次 |
| 2026-09-10 20:0x | 改用 `pythonw.exe` 消除控制台闪窗；触发句柄扩为 `@dsh` + `@dsh-main`（老板 19:46 用 `@dsh-main` 测试时规则未覆盖，未触发） |
