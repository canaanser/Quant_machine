#!/usr/bin/env node
// crew_review_merge —— **审阅→合入**这一步的自动化（老板 2026-09-12："这一步就不能自动化吗"）
//
// 思路：把"审阅判据"写成**可执行的门禁**，全绿才允许合；不全绿就叫人。
// 分工：`--check` 在沙箱内跑（只读 + npm test），写一张"合入申请"；
//      `--apply` 由**沙箱外小工**执行（它才有 .git 写权限和出网），照单合入并回板。
//
// 用法：
//   node scripts/crew_review_merge.mjs --check --repo D:\agent_crew_kits --branch feature/kit-m0 --task KIT-001
//   node scripts/crew_review_merge.mjs --apply            # 小工用：照 merge_request.json 执行
import fs from "fs";
import path from "path";
import { execFileSync } from "child_process";
import { fileURLToPath } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(HERE);
// 产物**不与通信用真源混放**（看板编辑 2026-09-12 建议）：单独放 outputs/merge/
const REQ = path.join(ROOT, "outputs", "merge", "merge_request.json");
const args = process.argv.slice(2);
const opt = (n, d = "") => { const i = args.indexOf(n); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const has = (n) => args.includes(n);
const nowIso = () => new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 19).replace("T", " ") + "+08:00";

const git = (repo, ...a) => execFileSync("git", ["-C", repo, "--no-optional-locks", ...a], { encoding: "utf8" }).trim();
// Windows 上跑 npm 必须走 shell（否则 spawn EINVAL）；命令是固定的 "npm test"，args 不经手。
const sh = (cwd, cmd, argv) =>
  execFileSync(cmd, argv, { cwd, encoding: "utf8", shell: process.platform === "win32", stdio: ["ignore", "pipe", "pipe"] });

function check(repo, branch, task, baseBranch, testsCmd, reviewPath, scopeArg) {
  const base0 = baseBranch || "main";
  const gates = [];
  const add = (name, ok, detail) => gates.push({ name, ok, detail });

  const base = git(repo, "rev-parse", "--abbrev-ref", "HEAD");
  const commits = git(repo, "log", "--oneline", `${base0}..${branch}`).split("\n").filter(Boolean);
  add("有没合入的提交", commits.length > 0, commits.length + " 个：\n  " + commits.join("\n  "));

  const files = git(repo, "diff", "--name-only", `${base0}...${branch}`).split("\n").filter(Boolean);
  add("变更面非空", files.length > 0, files.length + " 个文件");
  // 允许范围：给了 --scope 就只许在这些前缀内改（如 Hub 仓 = tools/mobile_chat/,docs/）；
  // 否则用默认红线（不许碰 spec/ 契约、不许碰 Hub 主体 board.mjs、不许跨到量化仓）。
  const scope = (scopeArg || "").split(",").map((s) => s.trim().replace(/\\/g, "/")).filter(Boolean);
  const bad = scope.length
    ? files.filter((f) => !scope.some((p) => f.startsWith(p)))
    : files.filter((f) => /^spec\//.test(f) || /board\.mjs$/.test(f) || /Quant_Alpha_System/.test(f));
  add(
    scope.length ? "改动都在允许范围内（" + scope.join(" / ") + "）" : "没碰契约 spec/ 与别的仓",
    bad.length === 0,
    bad.length ? "越界文件：" + bad.join(", ") : "干净"
  );

  const deleted = git(repo, "diff", "--name-status", `${base0}...${branch}`).split("\n").filter((l) => l.startsWith("D\t"));
  add("没有删除文件（废除只标记）", deleted.length === 0, deleted.length ? deleted.join("; ") : "无删除");

  // ★ 工作树与分支同步自检（2026-09-13 07:0x 加，PLT-007 那次真踩）：
  //   有人用"临时索引 + commit-tree"提交（分支指针动了、**工作树没动**），而回归是在**工作树**里跑的 →
  //   轻则 MODULE_NOT_FOUND、重则**拿旧代码跑绿**（最坏：门禁替一个没测过的版本背书）。
  //   判据：`git diff <branch> -- <本次变更的文件>` 必须为空（= 工作树里这些文件与分支一致）。
  //  边界：分支**已合入**（或空提交）时 files 为空 → 这条退化成"整树对比"会误报，所以显式跳过。
  const dirtyVsBranch = files.length
    ? git(repo, "diff", "--name-only", branch, "--", ...files).split("\n").filter(Boolean)
    : [];
  add(
    "工作树与分支同步（变更文件逐一比对）",
    dirtyVsBranch.length === 0,
    dirtyVsBranch.length
      ? "不同步：" + dirtyVsBranch.join(", ") +
        "\n  修法（只补这些文件）：git restore --source=" + branch + " --worktree -- " + dirtyVsBranch.join(" ")
      : (files.length ? "一致" : "无变更文件（分支已合入/空），跳过")
  );

  const who = git(repo, "log", `${base0}..${branch}`, "--format=%an <%ae>").split("\n").filter(Boolean);
  const allSigned = who.length > 0 && who.every((w) => /^codex-|^dsh-/.test(w));
  add("署名是注册的看板名", allSigned, who.join(" | "));

  // 回归命令可换（如 Hub 仓要跑 selftest_v2 183 + ui_check 44），默认 npm test
  const cmd = testsCmd || "npm test";
  let testOk = false, testTail = "", testDeferred = false;
  try {
    const out = execFileSync(cmd, { cwd: repo, encoding: "utf8", shell: true, stdio: ["ignore", "pipe", "pipe"] });
    testOk = true;
    testTail = String(out).split("\n").filter((l) => /pass|fail|通过/.test(l)).slice(-3).join(" ");
  } catch (e) {
    testTail = String(e.stdout || e.message).split("\n").slice(-6).join(" ");
    // 沙箱写不了别的仓（EPERM/EACCES）→ 不是测试失败，**交给 apply 阶段在沙箱外跑**。
    if (/EPERM|EACCES|operation not permitted|拒绝访问/i.test(testTail)) testDeferred = true;
  }
  add(
    testDeferred ? "回归交给沙箱外跑（本沙箱写不了该仓）" : "回归全绿：" + cmd,
    testOk || testDeferred,
    testDeferred ? "check 阶段跳过；apply 阶段在外层强制执行：" + cmd : testTail || "（无输出）"
  );

  // 审阅记录（AGENTS.md：合入 main 的审阅职责在 Codex 侧，留痕要能查到）
  if (reviewPath) {
    // 审阅记录可能**在分支上**（工作树还停在 main）→ 先按分支查 blob，再落回文件系统。
    const rel = reviewPath.replace(/\\/g, "/");
    let exists = false, where = "";
    try {
      const size = Number(git(repo, "cat-file", "-s", `${branch}:${rel}`));
      exists = size > 0;
      where = `${branch}:${rel}（${size}B）`;
    } catch {}
    if (!exists) {
      const rp = path.isAbsolute(reviewPath) ? reviewPath : path.join(ROOT, reviewPath);
      exists = fs.existsSync(rp) && fs.statSync(rp).size > 0;
      where = exists ? rp : "缺（分支与工作树都没有）：" + reviewPath;
    }
    add("有审阅记录文件", exists, where);
  } else {
    add("有审阅记录文件", true, "（未指定 --review，跳过）");
  }

  const ok = gates.every((g) => g.ok);
  const rec = {
    ts: nowIso(), task: task || "(未标)", repo, branch, base: base0, tests: cmd, review: reviewPath || null,
    head: (() => { try { return git(repo, "rev-parse", branch); } catch { return null; } })(),
    ok, gates, by: "codex-总监",
  };
  return rec;
}

function applyMerge() {
  if (!fs.existsSync(REQ)) return console.log("没有合入申请：" + REQ);
  const r = JSON.parse(fs.readFileSync(REQ, "utf8"));
  if (!r.ok) return console.log("申请未过门禁，不合。");
  const head = git(r.repo, "rev-parse", r.branch);
  if (head !== r.head) return console.log("分支已变动（审阅后有人提交），**不合**，请重跑 --check：" + head);
  // apply 在**沙箱外**执行 → 回归命令在这里真跑一遍（check 阶段可能因沙箱写不了而跳过）
  const tcmd = r.tests || "npm test";
  try {
    const out = execFileSync(tcmd, { cwd: r.repo, encoding: "utf8", shell: true, stdio: ["ignore", "pipe", "pipe"] });
    console.log("回归通过：" + tcmd + " → " + String(out).split("\n").filter((l) => /pass|fail|通过/.test(l)).slice(-2).join(" "));
  } catch (e) {
    console.log("✗ 回归失败，**不合**：" + tcmd + "\n" + String(e.stdout || e.message).split("\n").slice(-8).join("\n"));
    process.exitCode = 1;
    return;
  }
  git(r.repo, "switch", r.base || "main");
  const msg = `merge(${r.branch.split("/").pop()}): 合入 ${r.task}（自动门禁通过）`;
  const body = `自动合入：门禁 ${r.gates.filter((g) => g.ok).length}/${r.gates.length} 全绿，审阅人 ${r.by}，申请时间 ${r.ts}。`;
  execFileSync("git", ["-C", r.repo, "merge", "--no-ff", r.branch, "-m", msg, "-m", body], { encoding: "utf8" });
  execFileSync("git", ["-C", r.repo, "push", "origin", r.base || "main"], { encoding: "utf8" });
  const after = git(r.repo, "rev-parse", r.base || "main");
  fs.renameSync(REQ, REQ.replace(/\.json$/, `.done-${Date.now()}.json`));
  console.log(JSON.stringify({ merged: r.branch, main: after }, null, 2));
}

if (has("--apply")) applyMerge();
else {
  const repo = opt("--repo"), branch = opt("--branch"), task = opt("--task"), base = opt("--base", "main");
  const tests = opt("--tests"), review = opt("--review"), scope = opt("--scope");
  if (!repo || !branch) {
    console.error('用法：--check --repo <仓> --branch <分支> [--task <卡号>] [--tests "<回归命令>"] [--review <审阅记录路径>]');
    process.exit(2);
  }
  const rec = check(repo, branch, task, base, tests, review, scope);
  fs.mkdirSync(path.dirname(REQ), { recursive: true });
  fs.writeFileSync(REQ, JSON.stringify(rec, null, 2) + "\n", "utf8");
  console.log(`== 审阅门禁：${repo} ${branch}（${rec.task}）==`);
  for (const g of rec.gates) console.log(`  ${g.ok ? "PASS" : "FAIL"}  ${g.name}  —  ${String(g.detail).replace(/\n/g, " ")}`);
  console.log(rec.ok ? "\n✓ 全部通过 → 已写合入申请（小工可自动合入）" : "\n✗ 有门禁未过 → **不许合入**，请人来看");
  process.exit(rec.ok ? 0 : 1);
}
