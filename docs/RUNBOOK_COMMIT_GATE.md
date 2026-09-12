# 提交闸（pre-commit）· 登记与运维

> 老板 2026-09-13 07:0x：「**你就装吧**」→ 装在本仓，拦"今晚真出过"的两类事故。
> 落地：`codex-总监`｜实现：`.githooks/pre-commit`（sh 垫片）＋ `.githooks/crew_pre_commit.py`（判据）

## 一、拦什么（都是今晚的真实事故）

| # | 事故 | 现在的判据 |
| --- | --- | --- |
| ① | **署名不是实名看板名**：提权提交 → Git 回落到默认身份 `canaanser <632106943@qq.com>` → 门禁判"署名不合规"、白跑一轮（TRD-003 那次） | `user.name` **必须在名册**（`outputs/dialog/agents.json` 的看板名，或 `老板`）**且** `user.email` == `<该线 slug>@agents.canaanser.local`；不满足 → **拒提交**并打印修法 |
| ② | **在别人的分支上提交**：共享工作树被切到 `feature/trd-003-tail-exec-fix`，我没看分支就提交 → 落到量化线的分支 | 分支名前缀 → 拥有者（`trd-`→`codex-量化总监`、`hub-`→`codex-看板编辑`、`plt-`→`codex-总监`/`老板`、`kit-`→`codex-套件`、`net-`/`dat-`→`dsh-老员工`）；**提交者不是该拥有者 → 拒提交** |

**每次提交都会打印一行**：`当前分支 = … ｜ 提交者 = … <…>`（可见性，防止"不知道工作树被切走了"）。

## 二、怎么用（对所有人）

1. **先把身份设成自己**（一次性）：
   ```
   git config user.name  "<你的看板名>"
   git config user.email "<你的工号>@agents.canaanser.local"
   ```
   （你的看板名/工号见名册 `outputs/dialog/agents.json`；拿不准跑 `node tools/mobile_chat/whoami.mjs --me <看板名>`。）
2. **提交前顺手看一眼分支**：`git branch --show-current`（闸也会打印，但别等它拦）。
3. **提权提交（沙箱外）**：`-c user.name=… -c user.email=…` 一起带上，别让 Git 回落到默认身份。

## 三、绕过（只两种情形，且要留痕）

```
CREW_HOOK_BYPASS=1 git commit …
```
只允许：**① 老板本人操作**；② **紧急止血**（正在丢数据/重复下单/服务已死）——事后按红线补报（谁/为什么几时）。

## 四、回滚点（一行）

```
git config --unset core.hooksPath      # 立即停用提交闸（钩子文件仍在，随时可再开）
```

## 五、自测（不用真提交，直接跑钩子入口）

```
git -c user.name=canaanser -c user.email=632106943@qq.com hook run pre-commit   # 期望 exit 1（拒）
git hook run pre-commit                                                        # 期望 exit 0（放行）
```

## 六、已知边界

- **合并提交不走 pre-commit**（Git 的规矩）：`git merge` 生成的合并提交**不受本闸约束**（自动合入小工也在此列）；
- **只覆盖本仓**：其他仓（如 `D:\agent_crew_kits`）要装得各自装一次（套件线自己定）；
- **不改写历史**：此前用默认身份提交的那些 commit **保持原样**（红线：不追溯），从启用时点起生效。
