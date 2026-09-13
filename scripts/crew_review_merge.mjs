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
import os from "os";
import crypto from "crypto";

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
  //  ★ 2026-09-13 08:0x 修（`codex-看板编辑` 报的假红）：**按"内容"比对，不看是否已跟踪**——
  //   原来用 `git diff <branch> -- <path>`，对**新增（未跟踪）文件**一律报"不同步"，
  //   而它给的修法（`git restore --worktree`）又不入索引 → 重跑还是红，**任何带新文件的交付都会被假红**。
  //   现在：分支侧 blob = `git rev-parse <branch>:<path>`；工作树侧 blob = `git hash-object <path>`；相等即同步。
  const blobOf = (rev, p) => { try { return git(repo, "rev-parse", `${rev}:${p}`); } catch { return "(absent)"; } };
  const blobWs = (p) => {
    const fp = path.join(ROOT, repo, p);
    try {
      if (!fs.existsSync(fp) || fs.statSync(fp).isDirectory()) return "(absent)";
      return git(repo, "hash-object", "--", p);
    } catch { return "(absent)"; }
  };
  const dirtyVsBranch = files.filter((p) => blobOf(branch, p) !== blobWs(p));
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
  // ★ 证据指纹（老板 2026-09-13 08:0x："一次验证，上层不重跑"）：
  //   命令 + 退出码 + 输出 sha256 + 时间 + 机器 + **全文日志路径**；上层只校验指纹，不再重复跑同一份回归。
  let EV = null;
  const testHead = (() => { try { return git(repo, "rev-parse", branch); } catch { return null; } })();
  try {
    const out = execFileSync(cmd, { cwd: repo, encoding: "utf8", shell: true, stdio: ["ignore", "pipe", "pipe"] });
    testOk = true;
    testTail = String(out).split("\n").filter((l) => /pass|fail|通过/.test(l)).slice(-3).join(" ");
    EV = { cmd, code: 0, head: testHead, ts: nowIso(), host: os.hostname(),
           bytes: Buffer.byteLength(String(out), "utf8"),
           sha256: crypto.createHash("sha256").update(String(out), "utf8").digest("hex").slice(0, 16),
           log: writeTestLog(task, branch, String(out)) };
  } catch (e) {
    testTail = String(e.stdout || e.message).split("\n").slice(-6).join(" ");
    // 沙箱写不了别的仓（EPERM/EACCES）→ 不是测试失败，**交给 apply 阶段在沙箱外跑**。
    if (/EPERM|EACCES|operation not permitted|拒绝访问/i.test(testTail)) testDeferred = true;
    if (!testDeferred) {
      EV = { cmd, code: Number(e.status || 1), head: testHead, ts: nowIso(), host: os.hostname(),
             bytes: 0, sha256: null, log: writeTestLog(task, branch, String(e.stdout || e.message)) };
    }
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
    evidence: EV,
  };
  return rec;
}

function applyMerge() {
  if (!fs.existsSync(REQ)) return console.log("没有合入申请：" + REQ);
  const r = JSON.parse(fs.readFileSync(REQ, "utf8"));
  if (!r.ok) return console.log("申请未过门禁，不合。");
  const head = git(r.repo, "rev-parse", r.branch);
  if (head !== r.head) return console.log("分支已变动（审阅后有人提交），**不合**，请重跑 --check：" + head);
  // ★ 0) 已经合过就**直接归档**，不重复合入、也不白跑一遍回归（2026-09-13 07:5x 实测：会多造一个"空合并提交"）
  const baseName = r.base || "main";
  try {
    execFileSync("git", ["-C", r.repo, "merge-base", "--is-ancestor", r.head, baseName], { stdio: "ignore" });
    console.log(`ℹ 这条分支（${r.branch.split("/").pop()}）已经在 ${baseName} 里了 → 直接归档申请（不重复合入、不重跑回归）`);
    fs.renameSync(REQ, REQ.replace(/\.json$/, `.superseded-${Date.now()}.json`));
    return;
  } catch {}
  // ★ 一次验证（老板 2026-09-13 08:0x 拍）：check 阶段**已经真跑过**、且指纹对得上 → 这里**不重跑**，
  //   直接引用它的指纹（命令/退出码/sha256/时间/机器/全文日志）。对不上才真跑。
  const tcmd = r.tests || "npm test";
  const ev = r.evidence || null;
  const canReuse = !!(ev && ev.code === 0 && ev.head === r.head && ev.cmd === tcmd);
  if (canReuse) {
    console.log(`复用 check 阶段证据（不重跑）：${tcmd} → sha256=${ev.sha256} ${ev.bytes}B @${ev.host} ${ev.ts}｜全文 ${ev.log}`);
  }
  try {
    if (canReuse) throw { __skip: true };
    const out = execFileSync(tcmd, { cwd: r.repo, encoding: "utf8", shell: true, stdio: ["ignore", "pipe", "pipe"] });
    console.log("回归通过：" + tcmd + " → " + String(out).split("\n").filter((l) => /pass|fail|通过/.test(l)).slice(-2).join(" "));
  } catch (e) {
    if (e && e.__skip) { /* 复用证据，跳过重跑 */ }
    else {
    console.log("✗ 回归失败，**不合**：" + tcmd + "\n" + String(e.stdout || e.message).split("\n").slice(-8).join("\n"));
    process.exitCode = 1;
    return;
    }
  }
  // ── ★ 不碰工作树的合入（2026-09-13 07:4x；`codex-看板编辑` 报的死结 + L28 正解）──
  //   死结：**共享工作树里"工作树已含待合内容、而 HEAD 还没有"** → `git switch` + `git merge` 一律被判成
  //   "本地改动会被覆盖" → 抛异常、main 不前进（今晚连败十几拍就是这么来的）。
  //   改用纯对象操作：`merge-tree --write-tree` 算合并树 → `commit-tree` 造合并提交 →
  //   `update-ref`（带旧值 = CAS，防并发）→ `push`。**全程不切分支、不碰索引**。
  const base = r.base || "main";
  const baseBefore = git(r.repo, "rev-parse", base);
  const whoName = process.env.CREW_MERGE_NAME || "codex-总监";
  const whoMail = process.env.CREW_MERGE_EMAIL || "codex-director@agents.canaanser.local";
  let tree;
  try {
    tree = String(execFileSync("git", ["-C", r.repo, "merge-tree", "--write-tree", baseBefore, r.head], { encoding: "utf8" }))
      .split("\n")[0].trim();
  } catch (e) {
    console.log("✗ merge-tree 失败（多半有冲突），**不合**：\n" + String(e.stdout || e.message).split("\n").slice(-10).join("\n"));
    process.exitCode = 1;
    return;
  }
  const msg = `merge(${r.branch.split("/").pop()}): 合入 ${r.task}（自动门禁通过）`;
  const body = `自动合入（不碰工作树）：tree=${tree}；门禁 ${r.gates.filter((g) => g.ok).length}/${r.gates.length} 全绿，审阅人 ${r.by}，申请时间 ${r.ts}。`;
  const commit = String(execFileSync("git", ["-C", r.repo, "-c", `user.name=${whoName}`, "-c", `user.email=${whoMail}`,
    "commit-tree", tree, "-p", baseBefore, "-p", r.head, "-m", msg, "-m", body], { encoding: "utf8" })).trim();
  // CAS：base 没被别人推动才生效。**推不动就说明"别人已经合过了/基线动了"** → 归档申请、别再空转
  // （2026-09-13 07:4x：我手工合完之后小工又跑了一次，这句抛未捕获异常，日志只剩一坨 Node 栈 —— 现在包起来说人话）
  try {
    execFileSync("git", ["-C", r.repo, "update-ref", `refs/heads/${base}`, commit, baseBefore], { encoding: "utf8" });
  } catch (e) {
    const now = git(r.repo, "rev-parse", base);
    const already = (() => { try { execFileSync("git", ["-C", r.repo, "merge-base", "--is-ancestor", r.head, base], { stdio: "ignore" }); return true; } catch { return false; } })();
    console.log(`ℹ 放弃合入（${already ? "这条分支**已经在 base 里**了" : "base 被别人推进"}）：base=${now} 期望旧值=${baseBefore}`);
    try { fs.renameSync(REQ, REQ.replace(/\.json$/, `.superseded-${Date.now()}.json`)); } catch {}
    return;
  }
  try {
    execFileSync("git", ["-C", r.repo, "push", "origin", base], { encoding: "utf8" });
  } catch (e) {
    console.log("✗ push 失败（本地已合、远端未更新；**保留申请**，下一拍会重试）：\n" + String(e.stdout || e.message).split("\n").slice(-6).join("\n"));
    process.exitCode = 1;
    return;
  }

  // ② 只同步"本来干净"的文件：工作树里对该路径**没有本地改动**才覆盖；有本地改动的一律跳过（绝不覆盖别人）。
  const changed = git(r.repo, "diff", "--name-only", baseBefore, commit).split("\n").filter(Boolean);
  const skipped = [];
  for (const p of changed) {
    const cleanVsOld = isClean(r.repo, baseBefore, p);      // 工作树 == 合入前的 base
    const cleanVsNew = isClean(r.repo, commit, p);          // 工作树 == 合入后
    try {
      if (cleanVsOld) execFileSync("git", ["-C", r.repo, "restore", "--source=" + commit, "--staged", "--worktree", "--", p], { encoding: "utf8" });
      else if (cleanVsNew) execFileSync("git", ["-C", r.repo, "restore", "--source=" + commit, "--staged", "--", p], { encoding: "utf8" });
      else skipped.push(p);
    } catch (e) {
      skipped.push(p + "(同步失败)");
    }
  }
  const after = git(r.repo, "rev-parse", base);
  fs.renameSync(REQ, REQ.replace(/\.json$/, `.done-${Date.now()}.json`));
  console.log(JSON.stringify({ merged: r.branch, base: after, tree, commit, synced: changed.length - skipped.length, skipped }, null, 2));
}

/** 工作树里该路径是否与 <rev> 一致（= 没有本地改动）。 */
function isClean(repo, rev, p) {
  try {
    execFileSync("git", ["-C", repo, "diff", "--quiet", rev, "--", p], { encoding: "utf8", stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

/** 把回归**全文**落盘（上下文只留摘要，老板 2026-09-13 08:0x："大输出落盘、只回三行"）；返回相对路径。失败不影响门禁。 */
function writeTestLog(task, branch, text) {
  try {
    const dir = path.dirname(REQ);
    fs.mkdirSync(dir, { recursive: true });
    const safe = String(task || "task").replace(/[^\w.-]+/g, "_") + "-" +
                 String(branch || "").split("/").pop().replace(/[^\w.-]+/g, "_");
    const p = path.join(dir, `${safe}-${Date.now()}.test.log`);
    fs.writeFileSync(p, String(text || ""), "utf8");
    return path.relative(ROOT, p).replace(/\\/g, "/");
  } catch {
    return null;
  }
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
