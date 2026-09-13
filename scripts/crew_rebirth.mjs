#!/usr/bin/env node
/**
 * crew_rebirth.mjs —— **个人重生**（老板 2026-09-13 08:3x 定：「不是离职交接，是个人重生：
 * 全自动、资产不落、**号不变**、只有 ID 变」）
 *
 * 与「承接换人」的区别：
 *   · 承接换人（crew_succession）：**工号换代**（codex-kit → codex-kit2），旧号永不复用；
 *   · 个人重生（本脚本）：**看板名与工号都不变**，只把**实例（threadId）**换新——
 *     老的 threadId 推进 `failedThreadIds`（可追溯），新的写进 `threadId`。
 *
 * 为什么要重生：上下文越长越慢越贵、压缩后细节会淡。重开一条干净实例 + 一页重生包 = 身份与资产不断、脑子上限清零。
 *
 * 用法（`--hours N` = 差量窗口，默认 3）：
 *   node scripts/crew_rebirth.mjs --plan  --me codex-总监 [--hours 3]   # 生成「重生包 + 差量页」（不写名册）
 *   node scripts/crew_rebirth.mjs --apply --me codex-总监 --thread <新 threadId>   # 绑定新实例（写名册+留痕）
 *   node scripts/crew_rebirth.mjs --auto  --me codex-总监               # 全自动（差量没核过 → 不换绑）
 *
 * **老板 2026-09-13 08:4x 定（两条固化）**：
 *   · **「推过 ≠ 知道」**——叫醒水位只决定"还叫不叫你"，**不决定"你知不知道"**。所以重生包必须附
 *     **近 N 小时差量页**，新实例第一句回 `差量已核 N 条`，**对不上就不换绑**。
 *     （活样本：08:19 那次重生，新实例判"真未读=0"是对的，但拿旧状态报出三条**早已解决**的未结，
 *      因为它继承的是水位、不是内容。见 docs/LESSONS.md L34。）
 *   · **归档按钮归老板本人按**：Agent 只做「旧实例进 failedThreadIds + 改名标注 ·旧（待归档）」；
 *     新实例验过之前，旧窗是唯一回退面，**不许代按**。
 *
 * **全自动路线（2026-09-13 08:1x 实测确立）**：**不用 app 的"跨线程委派通道"建窗**（那条会写坏首回合），
 *   改由**壳外小工 `codex exec` 起一条无窗实例** —— 实测：工具建窗首回合 **1 条残项**（缺 `call_id`），
 *   而 `codex exec` 起的实例 **0 条残项** ✓。身份/资产仍靠**名册 + 重生包 + 信箱/门铃**（安全通道）落定。
 *   **代价**：这种实例**不在 UI 侧边栏**（看不见）；要"看得见的窗"，得人在 Codex 里点一次新建（平台动作）。
 */
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const ROSTER = path.join(ROOT, "outputs", "dialog", "agents.json");
const SUCCESSIONS = path.join(ROOT, "outputs", "dialog", "successions.ndjson");
const OUTDIR = path.join(ROOT, "docs", "reports");

const has = (f) => process.argv.includes(f);
const opt = (f, d = "") => { const i = process.argv.indexOf(f); return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
const now = () => new Date(Date.now() + 8 * 3600e3).toISOString().replace("Z", "+08:00");
const stamp = () => now().slice(0, 16).replace("T", " ");

function roster() { return JSON.parse(fs.readFileSync(ROSTER, "utf8")); }

/** ts（"YYYY-MM-DD HH:MM[:SS]"，+08:00）→ ms；解析不出返回 null。 */
function tsMs(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/.exec(String(s || ""));
  return m ? Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4] - 8, +m[5], +(m[6] || 0)) : null;
}

function readNdjson(p) {
  if (!fs.existsSync(p)) return [];
  return fs.readFileSync(p, "utf8").split("\n")
    .map((l) => l.trim()).filter(Boolean)
    .map((l) => { try { return JSON.parse(l); } catch { return null; } })
    .filter(Boolean);
}

const clip = (s, n = 80) => {
  const t = String(s || "").replace(/\s+/g, " ").trim();
  return t.length > n ? t.slice(0, n) + "…" : t;
};

/**
 * §三「未结」自动草稿（老板 2026-09-13 09:1x 定："积压不会自动跟着走"）。
 * 活样本：08:19 那次重生的 §三 交出去时原文就是 `（待填）`——**等于没交**，新实例只能从信箱自己拼。
 * 这里把散在**卡 / 信箱 / 合入队列 / 我最近一条板行**里的"我的活"抓成一页草稿：出发的人删改即可，不从空白写。
 */
function draftOpenItems(name, meta) {
  const slug = meta.slug || "";
  const out = [];
  const taskDir = path.join(ROOT, "docs", "tasks");                       // ① 卡：提到我，且还有"待…"
  let cards = [];
  try { cards = fs.readdirSync(taskDir).filter((f) => f.endsWith(".md")); } catch { /* 没有就算了 */ }
  for (const f of cards) {
    let t = "";
    try { t = fs.readFileSync(path.join(taskDir, f), "utf8"); } catch { continue; }
    if (!t.includes(name)) continue;
    const lines = t.split(/\r?\n/);
    let idx = -1;                                                     // 优先取卡里的「未结」小节，
    for (let i = 0; i < lines.length; i++) if (/^#{1,6}\s*.*未结/.test(lines[i])) idx = i;
    let picked = [];
    if (idx >= 0) {                                                   // 那里才是"欠着的活"，
      for (let i = idx + 1; i < lines.length && picked.length < 2; i++) {
        if (/^#{1,6}\s/.test(lines[i])) break;
        const l = lines[i].trim();
        if (!l || l.startsWith("<!--")) continue;
        picked.push(l.replace(/^\s*[-|]\s*/, ""));
      }
    }
    if (!picked.length) {                                             // 没有那一节，才退回关键词捞一句
      const pend = lines.filter((l) => /(待你|等你|待老板|待批|待验收|待人拍板|待合)/.test(l));
      if (pend.length) picked = [pend[pend.length - 1].trim().replace(/^\s*[-|]\s*/, "")];
    }
    if (!picked.length) continue;
    out.push(`- 卡 \`${f.replace(/\.md$/, "")}\`：${clip(picked.join(" / "), 70)}`);
  }
  const since = Date.now() - 24 * 3600e3;                                  // ② 信箱里点名要我动的信（近 24h）
  for (const r of readNdjson(path.join(ROOT, "outputs", "dialog", `pending_${slug}.ndjson`))) {
    const m = tsMs(r.ts);
    if (m === null || m < since) continue;
    if (!/(要你一句话|等你|待你|请批复|待批|请裁定)/.test(String(r.body || ""))) continue;
    out.push(`- 信 \`${r.ts}\`（${r.from || "?"}）：${clip(String(r.body), 70)}`);
  }
  const mdir = path.join(ROOT, "outputs", "merge");                        // ③ 没跑完的合入申请
  try {
    for (const f of fs.readdirSync(mdir)) {
      if (!/^merge_request.*\.json$/.test(f)) continue;
      let j = {};
      try { j = JSON.parse(fs.readFileSync(path.join(mdir, f), "utf8")); } catch { /* 坏文件也列出来 */ }
      out.push(`- 合入队列 \`${j.task || "?"}\`（${j.branch || "?"}）：${f}`);
    }
  } catch { /* 没有队列目录 */ }
  const mine = readNdjson(path.join(ROOT, "outputs", "dialog", "dialog.ndjson")).filter((r) => r.from === name);
  const last = mine[mine.length - 1];                                      // ④ 我最近一条板行（若写了"未结"）
  if (last && /未结/.test(String(last.body || ""))) out.push(`- 我最近一条板行（${last.ts}）：${clip(last.body, 90)}`);
  return out.slice(0, 12);
}

/**
 * ★ 2026-09-13 08:4x（老板："把他这次错的问题，用固化方法来解决"）——**差量页**。
 *
 * 根因不是新实例判错：**重生只继承了"叫醒水位"，没继承"内容"**。水位说"这封推过了"，新实例
 * 就当成"我知道了"，于是把旧实例在最后一小时里已经办结的事，又当成未结报给老板。
 *
 * 口径从此拆开（写进 AGENTS.md）：**水位管"还叫不叫你"，差量页管"你知不知道"**。
 */
function makeDelta(name, meta, hours) {
  const slug = meta.slug || "";
  const since = Date.now() - hours * 3600e3;
  const inWin = (r) => { const m = tsMs(r && r.ts); return m !== null && m >= since; };
  const mail = readNdjson(path.join(ROOT, "outputs", "dialog", `pending_${slug}.ndjson`))
    .filter(inWin)
    .map((r) => ({ ts: r.ts || "", src: `信·${r.from || "?"}`, text: clip(r.body) }));
  const board = readNdjson(path.join(ROOT, "outputs", "dialog", "dialog.ndjson"))
    .filter((r) => inWin(r) && (r.from === name || r.to === name))     // ★ 真源字段是 from/to（不是 author/target）
    .map((r) => ({ ts: r.ts || "", src: `板·${r.from || "?"}${r.to ? "→" + r.to : ""}`, text: clip(r.body) }));
  const rows = [...mail, ...board].sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
  let commits = [];
  try {
    commits = execFileSync("git", ["log", "--oneline", "--since=" + new Date(since).toISOString(), "main"],
      { cwd: ROOT, encoding: "utf8" }).split("\n").map((s) => s.trim()).filter(Boolean);
  } catch { /* 没 git 也不阻塞重生 */ }
  const file = path.join(OUTDIR, `REBIRTH_${slug}_${stamp().replace(/[-: ]/g, "")}.delta.md`);
  const sinceStr = new Date(since + 8 * 3600e3).toISOString().slice(0, 16).replace("T", " ");
  const tbl = (arr) => (arr.length ? arr.map((r) => `| ${r.ts} | ${r.src} | ${r.text} |`).join("\n") : "| — | — | 无 |");
  const total = mail.length + board.length;
  fs.writeFileSync(file, `# 差量页 · \`${name}\`（近 ${hours} 小时，起于 ${sinceStr}）

> **这一页 = 「旧实例读过、但交接包没写」的那一段。** 交接只交水位就会漏掉它（见 \`docs/LESSONS.md\` L34）。
> 口径：**叫醒水位只决定"还叫不叫你"，不决定"你知不知道"**——判"真未读=0"只说明**没有新信**，
> **不说明你知道这窗口里发生了什么**。这页才是内容。

## 一、窗口内的信箱（${mail.length} 条）

| ts | 来自 | 首行 |
| --- | --- | --- |
${tbl(mail)}

## 二、窗口内、与我有关的看板行（${board.length} 条）

| ts | 谁 | 首行 |
| --- | --- | --- |
${tbl(board)}

## 三、窗口内 main 的提交（${commits.length} 条）

${commits.length ? commits.map((c) => "- " + c).join("\n") : "- （无）"}

## 四、硬要求

> 新实例**第一句**必须回：\`差量已核 ${total} 条\`（共 ${mail.length} + ${board.length}）。
> 对不上 = 没读全 → **不换绑**（\`--auto\` 已按这条卡；窗口内又落了新信时容差 ±20%）。
> 未结清单里凡是被本页证伪的，**一律划掉**，别报给老板。
`, "utf8");
  return { rel: path.relative(ROOT, file).replace(/\\/g, "/"), hours,
           count: total, mail: mail.length, board: board.length };
}

function packFor(name, meta, delta) {
  const slug = meta.slug || "";
  const drel = delta ? delta.rel : "（差量页未生成——别开工，先让总监补）";
  const dmix = delta ? `近 ${delta.hours} 小时：信箱 ${delta.mail} 条 + 看板 ${delta.board} 条 = ${delta.count} 条` : "";
  const openItems = draftOpenItems(name, meta);
  return `# 重生包 · \`${name}\`（工号不变：${slug}）

> 老板 2026-09-13 08:3x：「**个人重生：全自动、资产不落、号不变、只有 ID 变**」。
> 生成时间：${stamp()}｜**这一页就是新实例的全部输入**（读完就能接手干活）。

## 一、我是谁（照名册真源，别记成别的）

- 看板名 **${name}**｜工号 **${slug}**｜层级 \`${meta.level || ""}\`｜领导 **${meta.leader || ""}**｜工位 \`${meta.workspace || ""}\`
- 我的下级：见 \`docs/ORG_CHART.md\`（**只给自己的下级派活**；别人的人只发"请求"）
- 上下文：**本实例是新生的（ID 已换）**；旧实例的账本仍在盘上可追溯（见 §四）。

## 二、接手第一件事：**照抄下面这几条命令**（一次一条，别跳、别自己发明）

\`\`\`powershell
cd ${meta.workspace || "E:\\stockgate\\Quant_Alpha_System"}

# ① 认身份（读名册真源：级别 / 必读 / 发言权）
node tools/mobile_chat/whoami.mjs --me ${name}

# ② 读差量页（近 ${delta.hours} 小时：信箱 ${delta.mail} + 看板 ${delta.board} = ${delta.count} 条）
#    它是"旧实例读过、交接包没写"的那一段 —— 先读它，再碰 §三 的未结
Get-Content "${drel}"

# ③ 读自己的信箱（**只读**：这是只追加真源，不删、不搬、不归档、不改一个字）
Get-Content "outputs/dialog/pending_${slug}.ndjson" -Tail 30

# ④ 回报一行（板行是单行存储；正文**先落文件**再发，别在命令行里拼正文）
#    先把正文写进 outputs/outbox/<自己起名>.txt，然后：
node tools/mobile_chat/say.mjs --file outputs/outbox/<你的正文>.txt --author ${name} --card - --to 老板 --flatten --max 200

# ⑤ 发之前自检：未结条目必须带"核于"戳
node scripts/evidence.mjs --check-file outputs/outbox/<你的正文>.txt
\`\`\`

- **要核一条事实**：\`node scripts/evidence.mjs --claim "<你在断言什么>" --cmd "<核它成立的命令>"\`（**退出码 0 = PASS**）；
- **本质只有三类操作**：**跑命令 / 读写文件 / 发消息**（板 \`/api/post\`、信 \`/api/mail\`、叫醒＝门铃 \`codex queue\`）。
  **没有第四类**——所以看到"清空信箱""推过""水位"这类**行话**，一律翻译成上面对应的具体动作；
  翻不出来就别做，回一行问清楚。
- **"推过"≠"知道"**：水位只决定"还叫不叫你"，**不决定你知不知道**；判"真未读=0"只说明没有新信，
  **不能代替读差量页**（这是踩过坑才加的，见 L34）。

## 三、未结（本线待办，重生不丢）

<!-- ★★ 下面是脚本自动抓的**草稿**（卡 / 信箱 / 合入队列 / 我最近一条板行）。
     **出发的人必须删改后再交，不许原样交出去**：① 已办结的划掉 ② 缺"等谁"的补上
     ③ 一条都没有就写"无"——**别留空白**（08:19 那次就是留了"（待填）"，等于没交）。
     判据：每条都要能对上差量页里的一条时间戳；对不上 = 过期未结，划掉，别报给老板。 -->
${openItems.length ? openItems.join("\n") : "- （自动草稿没抓到——**要么你手上真没有积压，要么它不在账上；后者更危险，自己写清楚**）"}

## 四、资产指针（都在盘上）

| 类别 | 位置 |
| --- | --- |
| 规约/索引 | \`AGENTS.md\`、\`docs/INDEX.md\`、\`docs/READING.md\` |
| 教训 | \`docs/LESSONS.md\` |
| 本线信箱 | \`outputs/dialog/pending_${slug}.ndjson\`（镜像 \`.private/${slug}/inbox.md\`） |
| 名册（我这一行） | \`outputs/dialog/agents.json\` |
| 换实例留痕 | \`outputs/dialog/successions.ndjson\` |
| 旧实例账本 | \`~/.codex/sessions\` 目录下任意层级的 \`rollout-*<旧 threadId>*.jsonl\`（只读追溯） |

## 五、铁律（五条，最短版）

1. **结论必须自己核**（区分"不存在／不许查／查错地方"）；
2. **信息直达**（谁发现谁广播；层级只管归属与权限）+ **少发公告**；
3. **一处事实只写一处**（卡=状态与判据、报告=证据原文、板行=结论+路径）；**报告头 5 行摘要**；**长度硬上限**（信≤800/板≤200/报告≤60 行）；
4. **提交**：\`git add -- <新文件>\` 后 \`git -c user.name=… -c user.email=… commit -- <路径>\`（共享工作树：**新文件必须先 add**，别裸 git commit）；
5. **老板的公告与门铃永远先处理**；**P0 只认"老板本人 + 真公告"**；
6. **"推过"≠"知道"**：换实例时**水位不继承内容** → 先读差量页；**报出去的未结，每条都要能对上时间戳**。

## 六、收尾（**只有老板能做**，别代按）

- **归档旧对话框 = 老板本人按**（Agent 不代按）：新实例被验过之前，旧窗是**唯一回退面**；
- **改两个窗口标题**（老板 2026-09-13 10:2x 定的两重意义）：**新窗**标题 = 岗位名（\`${name}\`）；
  **旧窗**标题 = 岗位名 + \`·旧（待归档）\`。用 \`set_thread_title\` 改（或老板在界面上点）。
- **旧窗（退役实例）= 老板的只读顾问**：它只与老板单线、只答问核事实，**不接受任何人的派活**。
  所以：**别把旧窗当依据**——你要引历史，就引盘上的账本 / 报告 / 卡（带时间戳的），**不引它的口头转述**。
`;
}

function plan(name, quiet) {
  const cfg = roster();
  const meta = (cfg.agents || {})[name];
  if (!meta) { console.error("名册里没有这条线：" + name); process.exit(3); }
  fs.mkdirSync(OUTDIR, { recursive: true });
  const hours = Number(opt("--hours", "3")) || 3;
  const delta = makeDelta(name, meta, hours);            // ★ 差量页先出，包再引它（L34）
  const file = path.join(OUTDIR, `REBIRTH_${meta.slug}_${stamp().replace(/[-: ]/g, "")}.md`);
  fs.writeFileSync(file, packFor(name, meta, delta), "utf8");
  const rel = path.relative(ROOT, file).replace(/\\/g, "/");
  console.log("① 重生包已生成：" + rel);
  console.log(`①' 差量页已生成：${delta.rel}（近 ${delta.hours} 小时：信箱 ${delta.mail} + 看板 ${delta.board} = ${delta.count} 条）`);
  if (!quiet) {
    console.log(`② 绑定新实例：node scripts/crew_rebirth.mjs --apply --me ${name} --thread <新 threadId>`);
    console.log(`   （或一步到位：node scripts/crew_rebirth.mjs --auto --me ${name}）`);
  }
  return { rel, delta };
}

function apply(name, tid) {
  if (!tid) { console.error("缺 --thread <新 threadId>"); process.exit(2); }
  const cfg = roster();
  const meta = (cfg.agents || {})[name];
  if (!meta) { console.error("名册里没有这条线：" + name); process.exit(3); }
  const old = meta.threadId || null;
  if (old === tid) { console.error("新 threadId 和旧的一样，没意义"); process.exit(2); }
  meta.threadId = tid;
  meta.failedThreadIds = Array.from(new Set([...(meta.failedThreadIds || []), ...(old ? [old] : [])]));
  meta.note = `${meta.note || ""}｜重生 ${stamp()}：实例 ${old ? old.slice(0, 8) : "(无)"} → ${tid.slice(0, 8)}（**看板名与工号不变**）`;
  fs.writeFileSync(ROSTER, JSON.stringify(cfg, null, 2) + "\n", "utf8");
  fs.appendFileSync(SUCCESSIONS, JSON.stringify({
    ts: stamp(), by: "codex-总监", kind: "rebirth", name, slug: meta.slug,
    fromThreadId: old, toThreadId: tid, reason: "上下文过长/换新实例（号不变）",
  }, null, 0) + "\n", "utf8");
  console.log("✓ 已绑定：" + name + " 的实例 " + (old ? old.slice(0, 8) : "(无)") + " → " + tid.slice(0, 8));
  console.log("✓ 旧实例已进 failedThreadIds（可追溯）；留痕：outputs/dialog/successions.ndjson");
  console.log("✓ 小工 30 秒内自检到名册变化 → 门铃自动敲新实例（无需重启计划任务）");
  console.log("⑤ 收尾（**只有老板能做**）：请老板在新实例验过之后，**本人按「归档」**旧对话框（不是删）；");
  console.log("   标题两重意义：**新窗 = 岗位名**、**旧窗 = 岗位名 + ·旧（待归档）**（set_thread_title 或老板点）；");
  console.log("   Agent 只做这两条 + 「进 failedThreadIds」（已自动）——**不代按归档**："
    + "新实例没验过之前，旧窗是唯一回退面。");
  console.log("   另：在看板留一行『" + name + " 已重生（号不变）』。");
}

/** 找最新的 codex.exe（更新后哈希目录会变，所以每次现找）。 */
function findCodex() {
  const pat = path.join(process.env.LOCALAPPDATA || "", "OpenAI", "Codex", "bin", "*", "codex.exe");
  const c = fs.globSync ? fs.globSync(pat) : [];
  return c.length ? c.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0] : null;
}

/** 扫出**全部** rollout 路径（用作"起实例前后"的集合差）。 */
function rolloutFiles() {
  const root = path.join(os.homedir(), ".codex", "sessions");
  const out = [];
  const walk = (d) => {
    let items = [];
    try { items = fs.readdirSync(d, { withFileTypes: true }); } catch { return; }
    for (const it of items) {
      const p = path.join(d, it.name);
      if (it.isDirectory()) walk(p);
      else if (/^rollout-.*\.jsonl$/.test(it.name)) out.push(p);
    }
  };
  walk(root);
  return out;
}

const tidOf = (p) => path.basename(p).replace(/\.jsonl$/, "").split("-").slice(-5).join("-");

/**
 * ★ 2026-09-13 08:15 修：**别再按 mtime 找"最新 rollout"** ——
 *   首次真跑时它撞上了**正在活跃的看板编辑会话**（人家刚被写过文件、mtime 最新），
 *   于是体检/自检都对着错的线做（幸好"没验证到→不换绑"兜住了，零变化）。
 *   现在用**起实例前后的集合差**：新出现的那个文件才是我起的实例 ✓。
 */
function freshRollout(before, after) {
  const fresh = after.filter((p) => !before.includes(p));
  if (!fresh.length) return null;
  fresh.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  return { p: fresh[0], name: path.basename(fresh[0]), tid: tidOf(fresh[0]) };
}

/** ★ 起一条**无窗实例**（绕开"工具委派通道"的首回合缺陷）。返回新 threadId。 */
function spawnHeadless(prompt) {
  const exe = findCodex();
  if (!exe) throw new Error("找不到 codex.exe");
  const env = { ...process.env, USERPROFILE: os.homedir(), HOME: os.homedir(),
                CODEX_HOME: path.join(os.homedir(), ".codex") };
  // ★ 2026-09-13 08:2x（老板："新生上一个实例他会带个名字，你直接找不就行了"）：
  //   用 `--json` —— 第一行就是 `{"type":"thread.started","thread_id":"…"}`，**ID 直接来自它自己**，
  //   不再靠"扫 sessions 目录猜最新文件"（那招撞过正在活跃的别家会话）。
  //   存活证明也用它自己的产出：**出现 turn.started + 一条 agent_message item.completed = 它真跑完一个回合** ✓。
  let out = "";
  try {
    out = String(execFileSync(exe, ["exec", "--json", "--skip-git-repo-check", "-"],
      { input: prompt, env, encoding: "utf8", timeout: 600000 }));
  } catch (e) { out = String((e && (e.stdout || e.message)) || ""); }
  const lines = out.split("\n").map((l) => l.trim()).filter(Boolean);
  let tid = null, turnStarted = false, gotMessage = false, lastMsg = "";
  for (const l of lines) {
    try {
      const ev = JSON.parse(l);
      if (ev.type === "thread.started" && ev.thread_id) tid = ev.thread_id;
      if (ev.type === "turn.started") turnStarted = true;
      if (ev.type === "item.completed" && ev.item && ev.item.type === "agent_message") {
        gotMessage = true;
        lastMsg = String(ev.item.text || lastMsg);        // ★ 留下它**自己说**的那段：体检要按内容判（L34）
      }
    } catch { /* 非 JSON 行忽略 */ }
  }
  if (!tid) throw new Error("没从 --json 事件里拿到 thread_id（实例可能没起来）：" + lines.slice(0, 3).join(" | ").slice(0, 200));
  const p = (rolloutFiles().find((x) => x.includes(tid))) || "(rollout 未落盘)";
  return { tid, p, alive: turnStarted && gotMessage, msg: lastMsg };
}

function auto(name, dry) {
  const cfg = roster();
  const meta = (cfg.agents || {})[name];
  if (!meta) { console.error("名册里没有这条线：" + name); process.exit(3); }
  const { rel: pack, delta } = plan(name, true);             // ① 重生包 + 差量页
  console.log("② 目标：起一条**无窗实例**（绕开工具委派通道；实测首回合 0 残项）");
  if (dry) { console.log("（--dry：不真起实例、不写名册）"); return; }
  const inst = spawnHeadless(`你是 ${name}（工号 ${meta.slug}）的**新生实例**。按顺序做三件：`
    + `① 读重生包 ${pack}；② 读差量页 ${delta.rel}（近 ${delta.hours} 小时、共 ${delta.count} 条）；`
    + `③ 回一段话——**第一行必须是「差量已核 ${delta.count} 条」**（数对不上就说明你没读全，会被判不通过），`
    + `后面是你按差量页核过的未结清单（每条带时间戳，被差量页证伪的直接划掉）。不要读别的文件。`);   // ②
  const tid = inst.tid;
  console.log("✓ 新实例 threadId = " + tid);
  const f = { p: inst.p };
  try {                                                      // ③ 体检（只读）
    const out = execFileSync("python", ["scripts/repair_callid_incident.py", "--rollout", f.p, "--thread", tid],
      { cwd: ROOT, encoding: "utf8" });
    console.log("③ 体检：" + String(out).split("\n").slice(-3).join(" ").trim());
  } catch (e) { console.log("③ 体检失败（不影响绑定）：" + String(e.message).slice(0, 120)); }
  // ④ **先确认它活着 + 差量核过，再换绑**（老板 08:2x："要是不成功呢？" → 不成功就一步都不写）
  //   判据两条：① 它自己的事件流里跑完了一整个回合（turn.started + agent_message）；
  //            ② 它**自己说**的那句话里有 `差量已核 N 条`，且 N 对得上（容差 ±20%，防窗口内又落新信）。
  //   —— 只判"活着"不够：活着的实例照样可能拿**过期状态**去指挥（L34 的活样本）。
  const ack = /差量已核\s*(\d+)\s*条/.exec(inst.msg || "");
  const ackN = ack ? Number(ack[1]) : null;
  const tol = Math.max(3, Math.round(delta.count * 0.2));
  const deltaOk = ackN !== null && Math.abs(ackN - delta.count) <= tol;
  if (!inst.alive || !deltaOk) {
    console.log(inst.alive
      ? `✗ **差量没核过 → 不换绑**：它回的是「${ackN === null ? "没有『差量已核 N 条』这句" : ackN + " 条"}」，`
        + `应为 ${delta.count} 条（容差 ±${tol}）。名册一个字没动，旧实例原样在岗。`
      : "✗ **没验证到它活着 → 不换绑**：名册一个字没动，旧实例原样在岗（资产/号/信箱全未变）。");
    console.log("  已起的那条无窗实例可以放着（无害），也可以按 rollout 路径归档：" + f.p);
    process.exitCode = 4;
    return;
  }
  apply(name, tid);                                          // ⑤ 绑定名册 + 留痕（同工号、只换 ID）
  console.log("⑤ 请交底：say.mjs --mail --wake --to " + name + " --file " + pack);
}

/** 确认新实例"真的活着"：给它的实例投一条门铃，看它有没有产生新回合（账本 mtime 前进）。 */
function waitAlive(name, meta, tid) {
  const exe = findCodex();
  if (!exe) return false;
  const mine = () => rolloutFiles().find((p) => p.includes(tid)) || null;
  const f0 = mine();
  const m0 = f0 ? fs.statSync(f0).mtimeMs : 0;
  const env = { ...process.env, USERPROFILE: os.homedir(), HOME: os.homedir(),
                CODEX_HOME: path.join(os.homedir(), ".codex") };
  try {
    execFileSync(exe, ["queue", "--thread", tid,
      "--message", `【自检】你已作为 ${name}（工号 ${meta.slug}）的新生实例就位。请回一行「我在」。`],
      { env, encoding: "utf8", timeout: 90000 });
  } catch { /* 投递失败也算"没验证到" */ }
  for (let i = 0; i < 20; i++) {                 // 最多等 60 秒
    const f = mine();
    if (f && fs.statSync(f).mtimeMs > m0) return true;      // ★ 只认**它自己**的账本有没有新回合
    try { execFileSync("sleep", ["3"]); } catch { /* Windows 无 sleep 命令 */ }
  }
  return false;
}

/** 一键回退：把 threadId 换回（默认取 failedThreadIds 里最后一个），并从 failed 列表里摘掉。 */
function rollback(name) {
  const cfg = roster();
  const meta = (cfg.agents || {})[name];
  if (!meta) { console.error("名册里没有这条线：" + name); process.exit(3); }
  const failed = meta.failedThreadIds || [];
  const to = opt("--to") || failed[failed.length - 1];
  if (!to) { console.error("没有可回退的旧 threadId（failedThreadIds 为空）"); process.exit(4); }
  const from = meta.threadId || null;
  meta.threadId = to;
  meta.failedThreadIds = failed.filter((x) => x !== to);
  meta.note = `${meta.note || ""}｜回退 ${stamp()}：实例 ${from ? from.slice(0, 8) : "(无)"} → ${to.slice(0, 8)}`;
  fs.writeFileSync(ROSTER, JSON.stringify(cfg, null, 2) + "\n", "utf8");
  fs.appendFileSync(SUCCESSIONS, JSON.stringify({
    ts: stamp(), by: "codex-总监", kind: "rebirth-rollback", name, slug: meta.slug,
    fromThreadId: from, toThreadId: to, reason: opt("--reason", "手动回退"),
  }) + "\n", "utf8");
  console.log(`✓ 已回退：${name} 的实例 ${from ? from.slice(0, 8) : "(无)"} → ${to.slice(0, 8)}（名字/工号/资产从未变过）`);
}

if (has("--rollback")) rollback(opt("--me"));
else if (has("--auto")) auto(opt("--me"), has("--dry"));
else if (has("--apply")) apply(opt("--me"), opt("--thread"));
else if (has("--plan")) plan(opt("--me"));
else {
  console.log("用法：");
  console.log("  node scripts/crew_rebirth.mjs --plan  --me <看板名>");
  console.log("  node scripts/crew_rebirth.mjs --apply --me <看板名> --thread <新 threadId>");
  console.log("  node scripts/crew_rebirth.mjs --auto  --me <看板名> [--dry]   # ★ 全自动（推荐）");
  console.log("  node scripts/crew_rebirth.mjs --rollback --me <看板名> [--to <旧 threadId>]  # 一键回退");
  console.log("  （以上都可加 --hours N 调差量窗口，默认 3 小时）");
  console.log("\n§两条硬规矩（老板 2026-09-13 08:4x 定）：");
  console.log("  · **「推过」≠「知道」**：重生包必附**近 N 小时差量页**；新实例第一句回 `差量已核 N 条`，"
    + "对不上（或没这句）→ **不换绑**；");
  console.log("  · **归档按钮归老板本人按**：Agent 只做「改名标注 ·旧（待归档）+ 进 failedThreadIds」，不代按。");
  console.log("\n§自动化边界（2026-09-13 08:1x 实测更新）：");
  console.log("  · **app 的跨线程委派通道有缺陷**：`create_thread`/`send_message_to_thread` 会在目标线写下一条"
    + "**缺 `call_id` 的 `function_call_output`** → 该线此后每轮 400（活样本 01a09817，工具建窗 1 条残项）；");
  console.log("  · **绕开它**：壳外小工用 `codex exec` 起**无窗实例** → 实测**首回合 0 残项**（样本 01a09819）✅；");
  console.log("  · 代价：这种实例**不在 UI 侧边栏**（看不见）。要「看得见的窗」就人在 Codex 里点一次新建；"
    + "身份/资产不依赖窗口（名册+信箱+门铃+重生包）。");
}
