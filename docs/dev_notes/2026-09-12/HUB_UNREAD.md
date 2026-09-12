# "未读口径"定稿 · codex-看板编辑（2026-09-12 23:3x）

## 一、口径（与宿主 `crew_host.py` 对齐）

> **未读 = 该线信箱里 ts 比它"本人上一次发言"更新的行。**

根因：信箱是 append-only 流水、没有已读概念。以前按**原始行数**算 → 几天前早回过几百遍的旧信
也算未读，芯片与门铃一路虚高（总监实测：清空后仍显示 10+；宿主也照着这个数反复叫同一批）。
两个必须排除的：

1. **`〔代答〕` 不算本人发言**——它是程序顶着本线名发的；否则代答一出，压在信箱里的留言就会被
   误判成"已处理"，这是"投递≠唤醒"从一个新口子漏回来。
2. **退役档案条目（`<看板名>·退役`）不叫、不计**——它不是活人，也没有"未读"这回事。

## 二、改了什么

`tools/mobile_chat/board.mjs`

- 新增 `lastOwnStatementTs(alias, records)`（本人上次发言，排除 `〔代答〕`，取最大 ts）。
- 新增 `pendingMailFor(alias, lastSeen)`（退役条目直接 0，其余走 `mailboxPendingFor`）。
- **三个接口统一走这两个函数**：`/api/employees`、`/api/contacts`、`/api/dialog`（页面芯片用的是
  `/api/dialog` 的 `agents[].pendingMail`）。以前三处各写一遍过滤，是漂移的温床。

`tools/mobile_chat/selftest_v2.mjs`：新增夹具线 `codex-测未读` + 5 条用例
（①旧留言算未读 ②本人发言后 N=0 ③真新留言 N=1 ④`〔代答〕`不算本人发言 ⑤退役条目 N=0）。
其中④是**判别性**用例：往真源写一条**比新留言更晚**的 `〔代答〕`，若被误算成"本人发言"，
那条新留言就会被吞掉（N 会变 0）。

## 三、验证

- `node tools/mobile_chat/selftest_v2.mjs` → **198/198**（190 → 192 补投修复 → 198 未读口径）
- `ui_check.py`（真页面 390x844）→ **44/44**

## 四、留下的坑（下次照这个做）

1. **`git switch` 在这个工作树会被挡住**：`tools/mobile_chat/` 在 `main` 上是未跟踪的，切分支时
   git 拒绝（"local changes would be overwritten"）。
2. **`git switch -f` 被安全审查否决**：工作树里压着别人 20+ 个未提交改动，`-f` 会一并丢。
3. **正确写法（临时索引 + `commit-tree`，完全不碰工作树与 HEAD）**：

   ```powershell
   $env:GIT_INDEX_FILE = (Join-Path $env:TEMP 'hub_plumb_index')
   git read-tree feature/hub-carry-layer
   git add -A -- tools/mobile_chat
   $tree = (git write-tree).Trim()
   $new  = (git commit-tree $tree -p (git rev-parse feature/hub-carry-layer).Trim() -F <msgfile>).Trim()
   git update-ref refs/heads/feature/hub-carry-layer $new
   Remove-Item Env:\GIT_INDEX_FILE
   ```

4. **断电时**：看板只能靠计划任务拉起（`Start-ScheduledTask QuantCodexBoard`，需提权）；
   `codex.exe` 路径随 App 升级变化，Hub 已改成动态解析。

## 五、待办（不在本次改动里）

- 口径尚未写进 `docs/DIALOG_HUB.md`（接口说明书），建议下轮补一段。
- 老板 23:1x 问"计划任务开关该在谁手上"：建议已当面给（按"断电时谁还能按下"分类；**停**要能离线按；
  小工只当"手"、总监当"嘴"、**不给看板编辑重启权**）。落地件等老板点头再动。
