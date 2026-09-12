# 操作手册：把「小工宿主」挂起来（老板执行部分）

> 我给到**能给的最后一步**；剩下的是**要管理员权限 + 沙箱外**的动作，只能你按。
> 宿主只做**搬运**（把各线信箱里压着的留言镜像到它的工位），**不碰引擎/托盘/stockdb**（脚本里有机器可验的自检）。

---

## 一、先看它要干什么（**只读，不改任何东西**）

```powershell
cd E:\stockgate\Quant_Alpha_System
E:\python\python.exe scripts\crew_host.py --once --dry-run
```

预期输出（示例）：

```
[DRY] mirror-mailbox: 跳过 dsh-main（工位不是 Windows 路径：/home/lgy/lab/股票）
[DRY] mirror-mailbox: codex-kit -> D:\agent_crew_kits\.private\codex-kit\inbox.md (2 条)
...
[DRY] heartbeat: ... workers=all mirror_total=0
```

**这一步不出任何文件**——看到的就是它准备做的事。

## 二、挂起来（要管理员 PowerShell）

**先看一眼它会注册什么**（不注册、不写任何东西）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\register_crew_host.ps1 -DryRun
```

预期打印：`Execute = E:\python\python.exe`、`Arguments = -B "…\scripts\crew_host.py" --once`、`Trigger = Once, repeat every 5 minute(s), indefinitely`、`Principal = current user (interactive), RunLevel Highest`。

**方式 A（推荐，稳）**：每 5 分钟跑一遍就退出（不怕进程死）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\register_crew_host.ps1
```

**方式 B**：登录时启动、常驻、每 300 秒一遍

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\register_crew_host.ps1 -Logon
```

（要更勤：`-Minutes 1`。）

## 三、验证（1–2 分钟后）

```powershell
Get-Content E:\stockgate\Quant_Alpha_System\outputs\crew_host_heartbeat.txt
Get-Content E:\stockgate\Quant_Alpha_System\outputs\crew_host_log.txt -Tail 20
Test-Path D:\agent_crew_kits\.private\codex-kit\inbox.md      # 套件线现在压着 2 条，应出现
```

**通过判据**：① 心跳时间在走；② 日志里有 `mirror-mailbox: codex-kit -> …`；③ 那个 `inbox.md` 存在。

## 四、日常开关

| 要做 | 命令 |
| --- | --- |
| 停（临时） | `schtasks /end /tn QuantCrewHost` |
| 起 | `schtasks /run /tn QuantCrewHost` |
| 卸载 | `powershell -NoProfile -ExecutionPolicy Bypass -File tools\register_crew_host.ps1 -Remove` |
| 只跑某一个小工 | `E:\python\python.exe scripts\crew_host.py --once --only heartbeat` |
| 干跑 | 加 `--dry-run` |

## 五、它会不会闯祸（边界）

1. **不调用任何进程控制**：源码里有 `self_guard()`，一旦出现 `taskkill/Start-Process/schtasks /run/…` 就**拒绝启动**；
2. **只写两类地方**：`outputs/crew_host_*`（它自己的状态与日志）、各工位的 `.private/<slug>/inbox.md`；
3. **跳过非 Windows 工位**（如 dsh 的 `/home/lgy/...`）——避免在 Windows 上乱造目录；
4. **幂等**：同一批留言只镜像一次（游标在 `outputs/crew_host_state.json`）；重跑不会重复写；
5. **可一键卸载**（见上表）。

## 六、回滚

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\register_crew_host.ps1 -Remove
Remove-Item E:\stockgate\Quant_Alpha_System\outputs\crew_host_state.json -Force   # 清游标（下次会重镜像最近 3 条）
```

**影响面**：只有本机该计划任务 + 那些 `inbox.md`（都是新增文件）；**不碰任何现有系统**。
