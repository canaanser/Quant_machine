# DSH 平台适配层 · 架构与可行性验证（codex-总监，2026-09-12）

> 老板指令：**"添加 DSH 的适配文件夹；你先做可行性验证，再把任务指派给 codex-套件；优先级高于它其他任务。"**
> 本文 = ①可行性结论（含实测证据）②要交付的目录结构 ③每个模块的契约与验收 ④红线。
> 落地形式：**不改内核、不改员工卡契约**，只新增 `adapters/dsh/` 一个平台目录。

---

## 一、可行性结论：**可行**（三条通路全部实测过）

| 通路 | 要验证什么 | 实测结果 | 证据 |
| --- | --- | --- | --- |
| **唤醒**（Codex→DSH） | 能不能不用 GUI、不用老板在场，把一句话投进 DSH 会话 | ✅ **可以**：`POST /api/session/prompt`（Web RPC），**冷会话也能唤** | `docs/reports/AR-001_arch.md` §三/§六（端到端实测：`accepted=true`，0.9–1.2s 出回复） |
| **文件**（写 DSH 工位） | Windows 能不能读写 WSL 里它的工位 | ✅ **可以**：`\\wsl.localhost\Ubuntu-24.04\home\lgy\...` 实测可访问；`wsl.exe -d Ubuntu-24.04 -- bash -lc` 实测可用 | 本人 2026-09-12 22:3x 实测：列出 `.dsh-bridge/.dsh-codex-bridge` 成功；`/home/lgy/lab/股票` 存在 |
| **回信**（DSH→Codex） | 它能不能主动投给我们的信箱 | ✅ **已经在上跑**：它能写 `/mnt/e/...`（同一份 `outputs/dialog/`），也可 `POST /api/mail` | `BRIDGE_REPLACEMENT.md` §二；今晚 DSH 侧的看板留言全程走这条路 |

### 1.1 DSH Web RPC 的准确形态（照这个实现，别猜）

1. **取 token**：读 WSL 里 `/home/lgy/.dsh-web.log` 的 `token=` 行（**每次 `dsh web` 重启会轮换**）；
2. **换 cookie**：`GET http://127.0.0.1:3080/?token=<token>`（Host 必须是 `127.0.0.1:3080`）→ `303` + `Set-Cookie: dsh-auth-<...>`；
3. **调用**：`POST /api/session/<method>`，头 = `content-type: application/json` + `Cookie:`，体 = 信封
   `{"type":"client-request","rpcId":"<uuid>","method":"session/<method>","payload":{"args":{...}}}`；
4. **方法**：`session/list`（列会话）、`session/prompt`（投一句话=按铃）、`session/create`（隔离测试用）；
5. **鉴权顺序**：Host/Origin 不过 → **403**；cookie 缺失/失效 → **401**（今天只读探测 `/`、`/api/sessions` 正是 401，**证明鉴权是活的**——别硬撞）。

### 1.2 已知缺口（不是"不可行"，是"要补的活"）

1. **`/home/lgy/.agent-crew/` 不存在**——DSH 员工卡里写的 `privateDir` 还是计划值，要由适配层创建并接管；
2. **它现在读的是 `outputs/inbox/*.task.json`**（`watch_bridge` 每 30s 扫），**不是**我们的 `pending_<slug>.ndjson`——镜像/投递要做**格式转换**；
3. **token 会轮换**：门铃必须"取不到 token → 明确报错并降级"（不许静默假装投了）；
4. **成本纪律（AR-001 实测）**：每次唤醒**重喂整份上下文**，DSH 主会话上下文可达 21.9 万 token。所以：**唤醒词极简（"在吗"级别）+ 少唤醒（事件驱动，不做保温心跳）**。

---

## 二、要交付的目录结构（**只加目录，不动内核**）

```
adapters/
└─ dsh/                          ← 平台目录（新增；平台差异全关在这里）
   ├─ README.md                  ← 平台总览：能力表 / 缺什么装什么 / 红线（本文精简版）
   ├─ platform.json              ← 平台描述：capabilities + 需要的适配器清单 + 版本
   ├─ wake/                      ← 【P0】Codex → DSH 按铃（Web RPC）
   │  ├─ index.mjs   └─ README.md
   ├─ mirror/                    ← 【P0】把 DSH 的信箱/工位文件镜像进 WSL，并把它写的投递回主干
   │  ├─ index.mjs   └─ README.md
   ├─ send/                      ← 【P1】DSH → Codex 发信的统一封装（写 /mnt/e 或 POST /api/mail）
   │  ├─ index.mjs   └─ README.md
   └─ selfcheck/                 ← 【P0】三连自检：门铃 / 信盒 / 回信，逐条出证据
      ├─ index.mjs   └─ README.md
```

**为什么按平台分组**（而不是散在 `inbound/`）：`inbound/session-inject|watch-file` 是**协议族**适配器（哪个平台都能装）；
`adapters/dsh/*` 是**平台私有**（知道 WSL 路径、知道 3080、知道 token 从哪读）。两者的关系：
**平台目录实现细节 → 复用 `adapters/_shared/adapter-kit.mjs` 的 probe/health/账本契约**。

---

## 三、每个模块的契约（照这个写）

**共同契约**（承自 `adapters/_shared/adapter-kit.mjs`，一条都不许省）：

1. 必须导出 `probe()`（能不能装）与 `health()`（装了还活不活）；
2. **probe 不过就不许装**；`hard=true` 的项全过才算过；
3. 一切动作写账本 `run/adapter-state/dsh-<模块>.ndjson`（谁、何时、投了什么、结果）；
4. **不许改 DSH 平台配置**（不装依赖、不改 `dsh web` 启动方式、不动它的库）；
5. **不许静默失败**：取不到 token / 连不上 3080 / 写不进工位 → 明确报错并降级，**并回看板一行**。

| 模块 | 干什么 | probe 判据 | 关键行为 |
| --- | --- | --- | --- |
| `wake` | 给 DSH 会话按铃 | ① 3080 可达（401 也算"服务在"）② 能读到 token ③ 换到 cookie | `prompt` 只投**极简指针**（"你信箱有 N 条，读 `inbox.md`"），不投正文；冷会话可唤 |
| `mirror` | 信盒双向搬运 | ① `\\wsl.localhost\...` 可写 ② `wsl.exe` 可用 | Codex→DSH：`pending_dsh-*.ndjson` → WSL 工位 `inbox.md` **+ DSH 认的 `outputs/inbox/*.task.json` 形态**；DSH→Codex：它写在 `/mnt/e/...` 的产出**归一进对话真源** |
| `send` | DSH 往 Codex 发信 | `/mnt/e/stockgate/Quant_Alpha_System/outputs/dialog` 可写 | 统一走 `pending_<slug>.ndjson`（带 `refs.transport="dsh-file"`），保留 `POST /api/mail` 作为备选 |
| `selfcheck` | 三连自检 | —— | ① 门铃：投一句"在吗"，**看它真的产生回合**（不是看 `accepted=true`）② 信盒：投一条进它工位并核它在板上回了一行 ③ 回信：它在 `/mnt/e` 落一行、我们读得到 |

---

## 四、验收标准（套件交活时按这个自证，我按这个验）

1. `npm test` 全绿（在现有 82 条基础上**至少补 12 条**：token 轮换/401/403/cookie 失效/写不进 WSL/格式转换/幂等/健康检查）；
2. **`probe` 与 `health` 都有实跑输出**（贴原始日志，不许"应该能行"）；
3. **端到端实证**：从 Codex 侧投一句话 → DSH 会话**真的产生回合**（证据：`session/list` 里该会话轮数 +1，或它的看板回帖）→ 它在 `/mnt/e` 落一行 → 我们读得到；
4. **降级实证**：故意让 token 失效/端口不可达 → 明确报错 + 看板一行，**不许静默**；
5. **零副作用**：不改 DSH 平台配置、不装依赖、不动它的库；`spec/` 契约不动（要动先报老板）。

## 五、红线（写进 `adapters/dsh/README.md`）

1. **不许改 DSH 平台配置**（`dsh web` 启动方式、它的依赖、它的配置）；
2. **token / cookie 不许进仓库、不许进日志正文**（cookie 落仓库外 0600 文件——承 AR-001 纪律）；
3. **唤醒要极简且要少**（重喂上下文很贵）：一棒只投指针，不做保温心跳；
4. **不许把 DSH 的"accepted"当"已唤醒"**——必须看到它产生回合才算；
5. DSH 侧层级上限是 `lead`（`org-levels.md` §六），**不给它 `merge-main`**。
