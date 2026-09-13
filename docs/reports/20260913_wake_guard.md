# `wake.mjs` 护栏 · 交付（老板 2026-09-13 09:4x 交办）

**结论（头 5 行）**

1. 护栏落点：`tools/mobile_chat/wake.mjs`——**目标线程 `source=vscode` 时禁止 `exec resume`**；`queue` 叫不醒就**报 `blocked`、退出码 4**，**不自己想办法**。
2. 机械判据：读会话账本**首行** `session_meta.payload.source`（`vscode`=有窗 / `exec`=无窗）；**判不出来一律按有窗**保守处理。
3. 依据：`AGENTS.md`「往线程里写字·合法通道只有三条」+ **L32 更正后的标题**「往 **app 会读的线程**里**程序写入** = 整类禁用」（原标题把对象指错，让人误以为"换个工具就绕开了"）。
4. 判别性用例 4/4：有窗→blocked(4)、无窗→resume(0)、source 缺失→blocked(4)、**有窗输出里没有任何 resume 动作**。
5. 真实账本复核：对我自己（`source=vscode`）→ blocked(4)；对 09:01 那条无窗实例（`source=exec`）→ resume 计划(0)。

## 一、改了哪几行（`tools/mobile_chat/wake.mjs`）

| 位置 | 改动 |
| --- | --- |
| 头注释 | 写明护栏与 L32 更正后的范围；把"没起就自动 resume"改成"**有窗禁止 resume**" |
| `sourceOf(tid)` | 新增：只读账本**首行**（262KB 块，不整读 40MB 大账本），取 `session_meta.payload.source` |
| 主流程尾段 | `queue` 未起回合时**按 source 分流**：`exec` 才走 resume；其余（`vscode`/空/其它）→ 打印 `blocked` 指引并 `exit 4` |
| `--self-test` / `--dry-run` / `--simulate-no-start` / `--sessions` | 新增：判别性自测与安全演练（**不执行任何真实动作**） |

## 二、为什么"判不出来"按有窗处理

搞错的代价**不对称**：把无窗误判成有窗 → 最多是"叫不醒、报 blocked"（人再想办法，**可恢复**）；
把有窗误判成无窗 → **那条线永久锁死**（每轮 400，已实测 3 次）。所以**判不准就往严的归**。

## 三、判别性用例（`--self-test`，4/4）

```
PASS  有窗（vscode） → 退出码 4、输出含「blocked」
PASS  无窗（exec）   → 退出码 0、输出含「exec resume」
PASS  source 缺失 → 按有窗保守处理 → 退出码 4、含「blocked」
PASS  有窗线程的输出里**没有任何 resume 动作**（只是警告文案里提到它）
```

> 第 4 条我第一版写错过：断言成"输出里没有 `resume` 这个词"，当场红——因为**护栏的警告文案本身**就会提到 `exec resume`。
> 判据必须盯**动作**（"打算 exec resume"/"已用 resume 叫醒"），不是盯词。

## 四、核于

- 核于 09:xx｜核法 `node tools/mobile_chat/wake.mjs --self-test`｜结果 **PASS**（4/4）
- 核于 09:xx｜核法 真实账本 dry-run（vscode 线程 + exec 线程各一条）｜结果 **PASS**（4 / 0）
