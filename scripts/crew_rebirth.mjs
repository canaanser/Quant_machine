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
 * 用法：
 *   node scripts/crew_rebirth.mjs --plan  --me codex-总监            # 生成「重生包」+ 打印后续三步（不写名册）
 *   node scripts/crew_rebirth.mjs --apply --me codex-总监 --thread <新 threadId>   # 绑定新实例（写名册+留痕+广播）
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

function packFor(name, meta) {
  const slug = meta.slug || "";
  return `# 重生包 · \`${name}\`（工号不变：${slug}）

> 老板 2026-09-13 08:3x：「**个人重生：全自动、资产不落、号不变、只有 ID 变**」。
> 生成时间：${stamp()}｜**这一页就是新实例的全部输入**（读完就能接手干活）。

## 一、我是谁（照名册真源，别记成别的）

- 看板名 **${name}**｜工号 **${slug}**｜层级 \`${meta.level || ""}\`｜领导 **${meta.leader || ""}**｜工位 \`${meta.workspace || ""}\`
- 我的下级：见 \`docs/ORG_CHART.md\`（**只给自己的下级派活**；别人的人只发"请求"）
- 上下文：**本实例是新生的（ID 已换）**；旧实例的账本仍在盘上可追溯（见 §四）。

## 二、接手第一件事（照做）

1. \`node tools/mobile_chat/whoami.mjs --me ${name}\` → 确认级别与必读；
2. 读 **\`AGENTS.md\`**（唯一规约真源，每轮自动加载）+ **\`docs/INDEX.md\`（一页索引）**；**其余按需 grep，别整读**；
3. 读我的信箱 \`outputs/dialog/pending_${slug}.ndjson\` → **清到 0 条**再干活（门铃报 N 条就清 N 条）；
4. 过一遍"未结"（§三）→ **先接在办**。

## 三、未结（本线待办，重生不丢）

<!-- 由本人填写或从卡/信箱同步；如实列，"无"就写无 -->
- （待填）

## 四、资产指针（都在盘上）

| 类别 | 位置 |
| --- | --- |
| 规约/索引 | \`AGENTS.md\`、\`docs/INDEX.md\`、\`docs/READING.md\` |
| 教训 | \`docs/LESSONS.md\` |
| 本线信箱 | \`outputs/dialog/pending_${slug}.ndjson\`（镜像 \`.private/${slug}/inbox.md\`） |
| 名册（我这一行） | \`outputs/dialog/agents.json\` |
| 换实例留痕 | \`outputs/dialog/successions.ndjson\` |
| 旧实例账本 | \`~/.codex/sessions/**/rollout-*<旧 threadId>*.jsonl\`（只读追溯） |

## 五、铁律（五条，最短版）

1. **结论必须自己核**（区分"不存在／不许查／查错地方"）；
2. **信息直达**（谁发现谁广播；层级只管归属与权限）+ **少发公告**；
3. **一处事实只写一处**（卡=状态与判据、报告=证据原文、板行=结论+路径）；**报告头 5 行摘要**；**长度硬上限**（信≤800/板≤200/报告≤60 行）；
4. **提交**：\`git add -- <新文件>\` 后 \`git -c user.name=… -c user.email=… commit -- <路径>\`（共享工作树：**新文件必须先 add**，别裸 git commit）；
5. **老板的公告与门铃永远先处理**；**P0 只认"老板本人 + 真公告"**。
`;
}

function plan(name, quiet) {
  const cfg = roster();
  const meta = (cfg.agents || {})[name];
  if (!meta) { console.error("名册里没有这条线：" + name); process.exit(3); }
  fs.mkdirSync(OUTDIR, { recursive: true });
  const file = path.join(OUTDIR, `REBIRTH_${meta.slug}_${stamp().replace(/[-: ]/g, "")}.md`);
  fs.writeFileSync(file, packFor(name, meta), "utf8");
  const rel = path.relative(ROOT, file).replace(/\\/g, "/");
  console.log("① 重生包已生成：" + rel);
  if (!quiet) {
    console.log(`② 绑定新实例：node scripts/crew_rebirth.mjs --apply --me ${name} --thread <新 threadId>`);
    console.log(`   （或一步到位：node scripts/crew_rebirth.mjs --auto --me ${name}）`);
  }
  return rel;
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
  console.log("⑤ 记得：**旧对话框归档**（不是删），并在看板留一行『X 已重生（号不变）』");
}

/** 找最新的 codex.exe（更新后哈希目录会变，所以每次现找）。 */
function findCodex() {
  const pat = path.join(process.env.LOCALAPPDATA || "", "OpenAI", "Codex", "bin", "*", "codex.exe");
  const c = fs.globSync ? fs.globSync(pat) : [];
  return c.length ? c.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0] : null;
}

/** 最新的 rollout 文件名 → 解析出 threadId（`rollout-<ts>-<tid>.jsonl` 的后 5 段）。 */
function newestRollout() {
  const root = path.join(os.homedir(), ".codex", "sessions");
  let best = null;
  const walk = (d) => {
    let items = [];
    try { items = fs.readdirSync(d, { withFileTypes: true }); } catch { return; }
    for (const it of items) {
      const p = path.join(d, it.name);
      if (it.isDirectory()) walk(p);
      else if (/^rollout-.*\.jsonl$/.test(it.name)) {
        const m = fs.statSync(p).mtimeMs;
        if (!best || m > best.m) best = { m, p, name: it.name };
      }
    }
  };
  walk(root);
  if (!best) return null;
  const tid = best.name.replace(/\.jsonl$/, "").split("-").slice(-5).join("-");
  return { ...best, tid };
}

/** ★ 起一条**无窗实例**（绕开"工具委派通道"的首回合缺陷）。返回新 threadId。 */
function spawnHeadless(prompt) {
  const exe = findCodex();
  if (!exe) throw new Error("找不到 codex.exe");
  const before = newestRollout();
  const env = { ...process.env, USERPROFILE: os.homedir(), HOME: os.homedir(),
                CODEX_HOME: path.join(os.homedir(), ".codex") };
  try {
    execFileSync(exe, ["exec", "--skip-git-repo-check", "-"],
      { input: prompt, env, encoding: "utf8", timeout: 600000, stdio: ["pipe", "pipe", "pipe"] });
  } catch (e) {
    // 非零退出也可能是"跑完但 warn"；只要出现了**新的 rollout** 就算起了实例
    if (!e || !e.stdout) throw e;
  }
  const after = newestRollout();
  if (!after || (before && after.p === before.p)) throw new Error("没有新 rollout，实例可能没起来");
  return after.tid;
}

function auto(name, dry) {
  const cfg = roster();
  const meta = (cfg.agents || {})[name];
  if (!meta) { console.error("名册里没有这条线：" + name); process.exit(3); }
  const pack = plan(name, true);                            // ① 重生包
  console.log("② 目标：起一条**无窗实例**（绕开工具委派通道；实测首回合 0 残项）");
  if (dry) { console.log("（--dry：不真起实例、不写名册）"); return; }
  const tid = spawnHeadless(`你是 ${name}（工号 ${meta.slug}）的**新生实例**。请读 ${pack} 并按它接手：`
    + `先跑 whoami、清空自己信箱、然后回报一行现状。不要读别的文件。`);   // ②
  console.log("✓ 新实例 threadId = " + tid);
  const f = newestRollout();
  try {                                                      // ③ 体检（只读）
    const out = execFileSync("python", ["scripts/repair_callid_incident.py", "--rollout", f.p, "--thread", tid],
      { cwd: ROOT, encoding: "utf8" });
    console.log("③ 体检：" + String(out).split("\n").slice(-3).join(" ").trim());
  } catch (e) { console.log("③ 体检失败（不影响绑定）：" + String(e.message).slice(0, 120)); }
  apply(name, tid);                                          // ④ 绑定名册 + 留痕（同工号、只换 ID）
  console.log("④ 请交底：say.mjs --mail --wake --to " + name + " --file <重生包路径>");
}

if (has("--auto")) auto(opt("--me"), has("--dry"));
else if (has("--apply")) apply(opt("--me"), opt("--thread"));
else if (has("--plan")) plan(opt("--me"));
else {
  console.log("用法：");
  console.log("  node scripts/crew_rebirth.mjs --plan  --me <看板名>");
  console.log("  node scripts/crew_rebirth.mjs --apply --me <看板名> --thread <新 threadId>");
  console.log("\n§自动化边界：**新建对话框**这一步目前只能人点（平台建窗工具据 L15/L21 有"
    + "『首回合缺 call_id 写坏线程』的已知缺陷）。若验证该缺陷已修，可把它也自动化。");
}
