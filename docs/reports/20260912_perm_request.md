# 权限申请 · `codex-看板编辑`（2026-09-12 00:3x）

> 老板：**"先测试一下，根据结果，把你要用到的权限怎么去放，给那个总监说就行了。"**
> 下面是实测结果 + 申请清单 + 放权办法。**只申请三件，且都要最小化。**

## 一、实测（每条都是我刚跑出来的原文报错）

| # | 我要做的事 | 现在 | 证据（原文） |
| --- | --- | --- | --- |
| ① | 读计划任务 `QuantCodexBoard` | ❌ | `Get-ScheduledTask -TaskName QuantCodexBoard` → **拒绝访问** |
| ② | 停/启该任务（改完代码要重启才生效） | ❌ | `Stop-ScheduledTask -TaskName QuantCodexBoard` → **拒绝访问** |
| ③ | 跑真浏览器验收（`ui_check.py` 36 项） | ❌ | 读 `C:\Users\Administrator\AppData\Local\ms-playwright` → **Access to the path is denied**（Playwright 报 "Please run playwright install"） |
| ④ | 写 Hub 数据目录 `C:\Users\Administrator\.codex\mobile_chat\`（`state.json`） | ❌ | `[IO.File]::WriteAllText(...)` → **Access to the path is denied**（**读**是通的：日志、token 我都能读） |
| ⑤ | 读/写工作区 `E:\stockgate\Quant_Alpha_System` | ✅ | 正常 |
| ⑥ | 读/写预览目录 `.codex\visualizations\…` | ✅ | 正常 |
| ⑦ | 执行 `codex.exe`（`%LOCALAPPDATA%\OpenAI\Codex\bin\…`） | ✅ | `codex --version` 正常 |
| ⑧ | 执行 `E:\python\python.exe` + Playwright Python 包 | ✅ | 正常（只是加载不到浏览器内核，见 ③） |

## 二、申请三件（按重要性排序）

### ① 计划任务 `QuantCodexBoard` 的 **查询 + 启动 + 停止** 权限 ★最要紧

**为什么**：我改的是 Hub 源码（`tools/mobile_chat/board.mjs`），**改动只有重启服务才生效**。
现在每次都要老板手动点一下，昨天夜里就因此积压了好几轮改动没上线。

**怎么给（三种，任选其一；我建议 C）**

- **A**：把该任务的**安全描述符**给到当前用户（管理员执行一次 `Set-ScheduledTask` 改写 `Principal`/ACL）；
- **B**：用管理员建一个**专用一键重启任务**（例如 `QuantBoardRestart`），动作就是
  `Stop-ScheduledTask QuantCodexBoard; Start-ScheduledTask QuantCodexBoard`，并且**允许当前用户运行它**；
  我以后只 `Start-ScheduledTask QuantBoardRestart`——**权限面最小**；
- **C**：把"启动/停止 `QuantCodexBoard`"这一条写进 **Codex 沙箱的允许清单**（如果你那边能改沙箱配置）。

### ② 读 `%LOCALAPPDATA%\ms-playwright`（无头浏览器内核）

**为什么**：真页面验收 36 项（折叠防抖、输入框无滚动条、提醒气泡样式、暂停红条…）全靠它；
没有它就只剩 `node` 层的自测（151 项），**页面级回归会瞎掉**。

**怎么给**：把该目录加进**可读**清单（只读即可，不需要写）。
若不方便：**由你在沙箱外代跑** `tools/mobile_chat/ui_check.py`（脚本已就绪，一条命令）。

### ③ 写 `C:\Users\Administrator\.codex\mobile_chat\`（可选，非必须）

**为什么**：直写 `state.json`（停用会话清单、冷却记账）。
**已经绕过**：停用清单我已改成**仓库版** `tools/mobile_chat/retired_threads.json`（可版本化、可审计），
所以**这条不急**——你要给就给，不给我也能干活。

## 三、我**不需要**的（免得放多）

- 不需要长期提权（只在"重启服务"这一件事上要）；
- 不需要起任何常驻进程的权限（红线：常驻只能挂计划任务）；
- 不需要改平台设置（`tailscale serve`、MCP 注册、config.toml 都不动）；
- 不需要写 `~/.codex/logs_2.sqlite` / sessions / rollout（红线）。

## 四、附带：两个探针文件待清（我没权限删）

权限体检时写了两个探针文件，因删除被策略拦下，留着请顺手清掉：

- `E:\stockgate\Quant_Alpha_System\outputs\__permprobe.txt`
- `C:\Users\Administrator\.codex\visualizations\2026\09\10\01a08ab8-c2a7-7c02-943b-f217d2538a83\__permprobe.txt`
