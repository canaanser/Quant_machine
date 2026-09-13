# 老板自己能跑的口令（复制即用）

> 都在仓库根目录 `E:\stockgate\Quant_Alpha_System` 下执行（PowerShell）。
> 说明：`codex.exe` 的哈希目录**每次升级会变**，所以下面的工具都**自己找**，你不用记路径。

## ① 叫醒任意一条线（门铃）

```powershell
cd E:\stockgate\Quant_Alpha_System
node tools/mobile_chat/wake.mjs --me codex-看板编辑 --msg "【门铃】请看一下你的信箱"
```
- 它会：找最新的 codex.exe → 补好环境变量 → **发门铃 → 验证对方真起了回合**；
  没起就**自动改用 resume**（无窗实例 `queue` 叫不醒，见 `LESSONS.md` L33）。
- 也可以直接给线程号：`--thread 01a09822-4632-7621-aee3-5779aae0b5af`

## ② 「有窗重生」三步（推荐）

> ⛔ **那句话必须由你亲手粘——Agent 一个字都不许替你粘。**
> 实测 **3 次**：任何**程序**往"有窗"线程里写字，都会留下一条 app 读不懂的记录
> （报错 `input: missing field call_id`），那条线**此后每轮 400、永久锁死**——
> 用 app 的跨线程工具会坏，用 `codex exec resume` 也会坏。
> **这不是"省事的写法"，是平台缺陷的必然要求。** 三条合法通道见 `AGENTS.md`「往线程里写字 · 合法通道只有三条」。

1. **你点一次**：Codex 里 **新建一个对话框**；
2. **你亲手把这一句粘进新窗**（把名字换成要重生的线）：
   ```
   读 docs/reports/REBIRTH_codex-director_202609130819.md，跑 node tools/mobile_chat/whoami.mjs --me codex-总监；然后把信箱读完、该办的办完、回看板一行现状。注意 pending_*.ndjson 是只追加真源——不删、不搬、不归档。
   ```
   （**别写"清空信箱"**：那四个字会被读成"删掉信箱文件"。正确意思是"读完、办完、回一行"，文件一个字不许动。）
3. **绑定**（回本窗/PowerShell 跑；`<新窗的 threadId>` 从新窗或账本拿）：
   ```powershell
   cd E:\stockgate\Quant_Alpha_System
   node scripts/crew_rebirth.mjs --apply --me codex-总监 --thread <新窗的 threadId>
   ```
   → 名册里 `codex-总监` 的实例换成新窗，**名字/工号/资产一字不变**，旧实例进 `failedThreadIds`。

**绑定之后**：叫醒走**门铃**（`codex queue`），或由你在这个窗里直接说话。
**不要再让任何工具"把话写进那个窗"**——那正是前面三次坏窗的同一个动作。

## ③ 回退（一键）

```powershell
cd E:\stockgate\Quant_Alpha_System
node scripts/crew_rebirth.mjs --rollback --me codex-总监
```

## ④ 无窗全自动重生（不用点窗）

```powershell
cd E:\stockgate\Quant_Alpha_System
node scripts/crew_rebirth.mjs --auto --me <看板名>          # 加 --dry 先干跑
```
代价：新实例**没有 UI 窗口**（但能被叫醒、能收发、能干活）。

## ⑤ 查某条线的实例 / 它最近有没有动作

```powershell
cd E:\stockgate\Quant_Alpha_System
node tools/mobile_chat/whoami.mjs --me codex-总监                    # 身份与必读
Get-ChildItem "$env:USERPROFILE\.codex\sessions" -Recurse -Filter "*<threadId>*" | Select-Object Name,LastWriteTime
```

## ⑥ 体检/救活"被写坏的线"（缺 call_id）

```powershell
cd E:\stockgate\Quant_Alpha_System
python scripts\repair_callid_incident.py --rollout <账本路径> --thread <threadId>          # 只读演练
python scripts\repair_callid_incident.py --rollout <账本路径> --thread <threadId> --apply  # 真改（先备份）
```
注意：**盘上修完要重启 Codex app 才会被重新加载**。
