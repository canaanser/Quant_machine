#!/usr/bin/env node
/**
 * evidence.mjs —— **「核于」戳**：把"我刚核过"变成一行可复算的证据。
 *
 * 为什么要有它（老板 2026-09-13 08:5x 定："报事实必须带核于戳"）：
 *   今天同一个病犯了两次 —— 08:39 报"`say-nofalsefail` 等门禁排期"（实际 08:40 已自动合入）、
 *   08:39 报"`main` 领先远端那 1 个提交"（实际 0/0）。根因不是判断错，是**报的是开口那一刻的快照**，
 *   而流水线是 30 秒粒度在动。**纪律靠人记是记不住的**，所以：核验要一条命令、结论要带时刻。
 *
 * 它和「门禁的证据指纹」不同：门禁那一套是**机器判合入**；这一套是**人报事实**（板行 / 信 / 报告 / 交活行）。
 *
 * 用法：
 *   # ① 单条：给一句断言 + 一条核它的命令（**退出码 0 = PASS**）
 *   node scripts/evidence.mjs --claim "PLT-007_dev.md 在 main" --cmd "git cat-file -e main:docs/reports/PLT-007_dev.md"
 *
 *   # ② 批量：每条一行，格式 `断言 || 命令`（写进文件，别在 shell 里拼正文）
 *   node scripts/evidence.mjs --batch outputs/outbox/my-claims.txt
 *
 *   # ③ 发出去之前自检：报告里"未结/待办"的每个条目，旁边必须有 `核于`
 *   node scripts/evidence.mjs --check-file outputs/outbox/my-report.md
 *
 * 输出（可直接粘进板行/信/报告）：
 *   核于 08:52｜核法 `git cat-file -e main:docs/reports/PLT-007_dev.md`｜结果 **PASS**｜日志 outputs/evidence/…
 *
 * 纪律（AGENTS.md「报事实必须带核于戳」）：
 *   · 凡报"未结 / 现状 / 已完成"，**每一条自带一行核于戳**；
 *   · **超过 10 分钟没重核的条目不许报** —— 宁可少报一条，也不许把"我上次看的时候"当事实；
 *   · 给老板的 "N 条未结"，N 只算**还在等**的（等老板拍板 / 等在办）。
 */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const LOGDIR = path.join(ROOT, "outputs", "evidence");

const has = (f) => process.argv.includes(f);
const opt = (f, d = "") => { const i = process.argv.indexOf(f); return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
const hhmm = () => new Date(Date.now() + 8 * 3600e3).toISOString().slice(11, 16);
const clip = (s, n = 60) => { const t = String(s || "").replace(/\s+/g, " ").trim(); return t.length > n ? t.slice(0, n) + "…" : t; };

/** 跑一条核验命令。**约定：退出码 0 = PASS**（判据一律写成"成立则返回 0"的形态）。 */
function run(cmd) {
  try {
    const out = String(execSync(cmd, { cwd: ROOT, encoding: "utf8", stdio: "pipe" }));
    return { ok: true, out };
  } catch (e) {
    return { ok: false, out: String((e && (e.stdout || e.stderr)) || e.message || "") };
  }
}

function logIt(claim, cmd, ok, out) {
  fs.mkdirSync(LOGDIR, { recursive: true });
  const id = crypto.createHash("sha1").update(claim + cmd).digest("hex").slice(0, 8);
  const file = path.join(LOGDIR, `${hhmm().replace(":", "")}-${id}.log`);
  fs.writeFileSync(file, `# claim: ${claim}\n# cmd:   ${cmd}\n# 核于:   ${hhmm()} (+08:00)\n# 结果:   ${ok ? "PASS" : "FAIL"}\n\n${out}\n`, "utf8");
  return path.relative(ROOT, file).replace(/\\/g, "/");
}

function stamp(claim, cmd) {
  const { ok, out } = run(cmd);
  const log = logIt(claim, cmd, ok, out);
  console.log(`核于 ${hhmm()}｜核法 \`${clip(cmd)}\`｜结果 **${ok ? "PASS" : "FAIL"}**｜日志 ${log}`);
  if (!ok) {
    console.log(`  ↑ 断言没成立：「${clip(claim, 80)}」——**这条不许报**（或改写成事实后重核）。`);
    console.log("  命令输出（末 3 行）：" + out.split("\n").filter((l) => l.trim()).slice(-3).join(" | ").slice(0, 240));
  }
  return ok;
}

/** 发出去之前自检：「未结 / 待办 / 在办」小节里的每个条目，旁边必须有 `核于`。 */
function checkFile(p) {
  const abs = path.isAbsolute(p) ? p : path.join(ROOT, p);
  if (!fs.existsSync(abs)) { console.error("找不到文件：" + p); process.exit(2); }
  const lines = fs.readFileSync(abs, "utf8").split(/\r?\n/);
  const bad = [];
  let inBlock = false, items = 0, stamped = 0;
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (/^#{1,6}\s/.test(l)) { inBlock = /(未结|待办|在办|待处理)/.test(l); continue; }
    if (!inBlock) continue;
    if (!/^\s*(?:[-*]|[①②③④⑤⑥⑦⑧⑨⑩]|\d+[.、)）])\s*\S/.test(l)) continue;
    items++;
    // 戳只认**这条自己的**：本行 + 紧跟其后的 3 行，遇到下一条/下一个标题就截断
    // （★ 自测抓到过：把上一条的戳算到下一条头上 → 假"合格"）
    const own = [l];
    for (let j = i + 1; j < lines.length && j <= i + 3; j++) {
      const l2 = lines[j];
      if (/^#{1,6}\s/.test(l2) || /^\s*(?:[-*]|[①②③④⑤⑥⑦⑧⑨⑩]|\d+[.、)）])\s*\S/.test(l2)) break;
      own.push(l2);
    }
    if (/核于/.test(own.join(" "))) stamped++; else bad.push(clip(l, 70));
  }
  console.log(`自检：未结/待办条目 ${items} 条，带「核于」戳 ${stamped} 条。`);
  if (bad.length) {
    console.log(`✗ **${bad.length} 条没戳，不许发**：`);
    for (const b of bad) console.log("  · " + b);
    console.log("  拿戳：node scripts/evidence.mjs --claim \"<断言>\" --cmd \"<核它成立的命令>\"");
    process.exit(1);
  }
  if (!items) console.log("（这条报告里没有未结/待办小节；若你其实报了未结，请用 `## 未结` 作小节标题。）");
  console.log("✓ 可以发。");
}

// ---- 入口 ----
if (has("--check-file")) { checkFile(opt("--check-file")); }
else if (has("--batch")) {
  const p = opt("--batch");
  const abs = path.isAbsolute(p) ? p : path.join(ROOT, p);
  if (!fs.existsSync(abs)) { console.error("找不到批量文件：" + p); process.exit(2); }
  const rows = fs.readFileSync(abs, "utf8").split(/\r?\n/).map((l) => l.trim()).filter((l) => l && !l.startsWith("#"));
  let allOk = true;
  console.log("```");
  for (const r of rows) {
    const [claim, cmd] = r.split("||").map((s) => (s || "").trim());
    if (!claim || !cmd) { console.log(`（跳过，缺 \`||\` 分隔：${clip(r)}）`); continue; }
    const { ok, out } = run(cmd);
    const log = logIt(claim, cmd, ok, out);
    console.log(`核于 ${hhmm()}｜核法 \`${clip(cmd)}\`｜结果 **${ok ? "PASS" : "FAIL"}**｜日志 ${log}`);
    if (!ok) { allOk = false; console.log(`  ↑ 「${clip(claim, 70)}」不成立，**不许报这条**`); }
  }
  console.log("```");
  if (!allOk) process.exit(1);
} else if (opt("--claim") || opt("--cmd")) {
  const claim = opt("--claim"), cmd = opt("--cmd");
  if (!claim || !cmd) { console.error("要同时给 --claim 和 --cmd"); process.exit(2); }
  if (!stamp(claim, cmd)) process.exit(1);
} else if (has("--in-main")) {
  // 今天两次踩的正是这一类：拿现成的两条捷径，省得为"怎么写才退出 0"纠结。
  const v = opt("--in-main");
  const cmd = /^[0-9a-f]{7,40}$/.test(v) ? `git merge-base --is-ancestor ${v} main` : `git cat-file -e main:${v}`;
  if (!stamp(`在 main：${v}`, cmd)) process.exit(1);
} else if (has("--ahead")) {
  const cmd = "git rev-list --count origin/main..main";
  const n = Number((run(cmd).out || "0").trim()) || 0;
  const ok = n > 0;
  const log = logIt("main 领先 origin/main", cmd, ok, String(n));
  console.log(`核于 ${hhmm()}｜核法 \`${cmd}\`｜结果 **${ok ? "PASS" : "FAIL"}**（实际领先 ${n} 个）｜日志 ${log}`);
  if (!ok) console.log('  ↑ main 与远端一致：**「要不要推」这条不用报**（今天就撞过一次）。');
} else {
  console.log("用法：");
  console.log("  单条   node scripts/evidence.mjs --claim \"<断言>\" --cmd \"<核它成立的命令>\"");
  console.log("  批量   node scripts/evidence.mjs --batch <文件>        # 每行：断言 || 命令");
  console.log("  自检   node scripts/evidence.mjs --check-file <待发的报告>");
  console.log("  捷径   node scripts/evidence.mjs --in-main <路径|短hash>   # 在不在 main");
  console.log("         node scripts/evidence.mjs --ahead                  # main 领先远端几个");
  console.log("\n约定：**命令退出码 0 = PASS**（判据写成「成立则返回 0」的形态）。");
  console.log("纪律：**超过 10 分钟没重核的条目不许报**——宁可少报一条，也不许把「我上次看的时候」当事实。");
}
