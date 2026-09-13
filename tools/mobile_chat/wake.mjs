#!/usr/bin/env node
/**
 * wake.mjs —— **管理员/老板自己敲门铃**（不用记 codex.exe 的哈希路径）
 *
 * 用法：
 *   node tools/mobile_chat/wake.mjs --me codex-看板编辑 --msg "【门铃】请看一下你的信箱"
 *   node tools/mobile_chat/wake.mjs --thread 01a09822-4632-7621-aee3-5779aae0b5af --msg "在吗"
 *
 * 做三件对的事（别的工具踩过的坑都补上了）：
 *   ① 自己找最新的 codex.exe（更新后哈希目录会变）；
 *   ② 补上 USERPROFILE/HOME/CODEX_HOME（缺了会报 "Could not find home directory"）；
 *   ③ **投完验证对方"真起了回合"**（看它自己的 rollout 账本 mtime 有没有前进）。
 *
 * ★★ 护栏（老板 2026-09-13 09:4x 交办，落实 `AGENTS.md`「往线程里写字·合法通道只有三条」）：
 *   **有窗线程（`session_meta.payload.source = vscode`）禁止 `exec resume`**——那正是"程序往 app 会读的
 *   线程里写正文"，会留下 app 读不懂的记录 → 该线**每轮 400、永久锁死**（已实测 3 次）。
 *   所以本工具：**有窗只许 `queue`**；叫不醒就**报 `blocked` 并退出码 4**，**不许自己想办法**。
 *   （L32 更正后的标题：「往 **app 会读的线程**里**程序写入** = 整类禁用」——与用哪个工具无关。）
 *   `--self-test` 是判别性用例：有窗必须 blocked、无窗才允许 resume、判不出来按有窗处理。
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
let ROSTER = path.join(ROOT, "outputs", "dialog", "agents.json");
let SESSIONS = path.join(os.homedir(), ".codex", "sessions");

const opt = (f, d = "") => { const i = process.argv.indexOf(f); return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
const has = (f) => process.argv.includes(f);
// 自测用的覆盖点（只影响本工具的读取，不碰真源）
if (opt("--roster")) ROSTER = opt("--roster");
if (opt("--sessions")) SESSIONS = opt("--sessions");

function findCodex() {
  const pat = path.join(process.env.LOCALAPPDATA || "", "OpenAI", "Codex", "bin", "*", "codex.exe");
  const c = fs.globSync ? fs.globSync(pat) : [];
  return c.length ? c.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0] : null;
}
function rollout(tid) {
  const hits = (fs.globSync ? fs.globSync(path.join(SESSIONS, "**", `rollout-*${tid}*.jsonl`)) : []);
  return hits.length ? hits.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0] : null;
}
const mtime = (p) => { try { return p ? fs.statSync(p).mtimeMs : 0; } catch { return 0; } };

function tidFor(name) {
  try { return (JSON.parse(fs.readFileSync(ROSTER, "utf8")).agents || {})[name]?.threadId || ""; } catch { return ""; }
}

/** 机械判据：读会话账本**首行**的 `session_meta.payload.source`。
 *  vscode = **有窗**（禁止 ③）／exec = **无窗**（③可用）。
 *  只读第一块（大账本 40MB，别整读）；**判不出来返回 ""**，调用侧按**有窗**保守处理。 */
function sourceOf(tid) {
  const p = rollout(tid);
  if (!p) return "";
  let fd;
  try {
    fd = fs.openSync(p, "r");
    const buf = Buffer.alloc(262144);
    const n = fs.readSync(fd, buf, 0, buf.length, 0);
    const first = buf.subarray(0, n).toString("utf8").split("\n")[0];
    return String((JSON.parse(first) || {}).payload?.source || "");
  } catch { return ""; } finally { if (fd !== undefined) try { fs.closeSync(fd); } catch {} }
}

/** 判别性自测：有窗必须 blocked、无窗才允许 resume、判不出来按有窗处理。成立返回 0。 */
function selfTest() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "wake-guard-"));
  const sess = path.join(tmp, "sessions"); fs.mkdirSync(sess, { recursive: true });
  const cases = [
    ["aaaaaaaa-1111-1111-1111-111111111111", "vscode",  4, "blocked", "有窗（vscode）"],
    ["bbbbbbbb-2222-2222-2222-222222222222", "exec",    0, "exec resume", "无窗（exec）"],
    ["cccccccc-3333-3333-3333-333333333333", undefined, 4, "blocked", "source 缺失 → 按有窗保守处理"],
  ];
  for (const [tid, source, , , ] of cases) {
    const payload = { session_id: tid, cwd: tmp };
    if (source) payload.source = source;
    fs.writeFileSync(path.join(sess, `rollout-2026-09-13T00-00-00-${tid}.jsonl`),
      JSON.stringify({ type: "session_meta", payload }) + "\n", "utf8");
  }
  let bad = 0;
  for (const [tid, , wantCode, wantText, label] of cases) {
    let out = "", code = 0;
    try {
      out = String(execFileSync(process.execPath, [fileURLToPath(import.meta.url),
        "--thread", tid, "--sessions", sess, "--simulate-no-start", "--dry-run"],
        { encoding: "utf8", timeout: 60000, stdio: ["ignore", "pipe", "pipe"] }));
    } catch (e) { code = e.status || 1; out = String((e.stdout || "") + (e.stderr || "")); }
    const ok = code === wantCode && out.includes(wantText);
    if (!ok) bad++;
    console.log((ok ? "PASS  " : "FAIL  ") + label + ` → 退出码 ${code}（期望 ${wantCode}）、输出含「${wantText}」`);
    if (!ok) console.log("      实际输出：" + out.replace(/\s+/g, " ").slice(0, 160));
  }
  // 反向断言：有窗那条**绝不能**出现 resume **动作**
  //   ⚠️ 不能简单断言"输出里没有 resume 这个词"——护栏的**警告文案**本身就会提到 `exec resume`。
  //     判据要盯**动作**：不许出现"打算 exec resume / 已用 resume 叫醒"。
  let winOut = "";
  try {
    winOut = String(execFileSync(process.execPath, [fileURLToPath(import.meta.url),
      "--thread", cases[0][0], "--sessions", sess, "--simulate-no-start", "--dry-run"],
      { encoding: "utf8", timeout: 60000, stdio: ["ignore", "pipe", "pipe"] }));
  } catch (e) { winOut = String((e.stdout || "") + (e.stderr || "")); }
  const noResume = !/打算 exec resume|已用 resume 叫醒/.test(winOut);
  if (!noResume) bad++;
  console.log((noResume ? "PASS  " : "FAIL  ") + "有窗线程的输出里**没有任何 resume 动作**（只是警告文案里提到它）");
  try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {}
  console.log(`\n自测结果：${bad === 0 ? "全部通过" : "失败 " + bad + " 条"}`);
  return bad === 0 ? 0 : 1;
}

const DRY = has("--dry-run");
const SIM_NO_START = has("--simulate-no-start");

if (has("--self-test")) process.exit(selfTest());

const name = opt("--me");
const tid = opt("--thread") || (name ? tidFor(name) : "");
const msg = opt("--msg") || "【门铃】请看一下你的信箱。";
if (!tid) { console.error("用法：--me <看板名> 或 --thread <threadId>，另加 --msg \"…\""); process.exit(2); }

const exe = findCodex();
if (!exe) { console.error("找不到 codex.exe"); process.exit(3); }
const env = { ...process.env, USERPROFILE: os.homedir(), HOME: os.homedir(), CODEX_HOME: path.join(os.homedir(), ".codex") };
const f0 = rollout(tid);
const m0 = mtime(f0);

let code = 0;
if (DRY || SIM_NO_START) {
  console.log(`[dry] 打算 queue --thread ${tid}（通道②：只递叫醒提示，不改写历史）`);
} else {
  try { execFileSync(exe, ["queue", "--thread", tid, "--message", msg], { env, encoding: "utf8", timeout: 90000 }); }
  catch (e) { code = 1; }
}

let started = false;
for (let i = 0; i < 8 && code === 0 && !DRY && !SIM_NO_START; i++) {
  if (mtime(rollout(tid)) > m0) { started = true; break; }
  try { execFileSync("ping", ["-n", "2", "127.0.0.1"], { stdio: "ignore" }); } catch {}
}
if (started) { console.log(`✓ 已叫醒 ${name || tid.slice(0, 8)}（queue 生效，账本已前进）`); process.exit(0); }

// ── 到这里 = queue 受理了但**没起回合**：按"有没有窗"分流（护栏） ────────────────
const src = opt("--source") || sourceOf(tid);
const windowed = src !== "exec";     // exec = 无窗（③可用）；vscode / 空 / 其它 → 一律按**有窗**保守处理
if (windowed) {
  console.error(`✗ blocked：${name || tid.slice(0, 8)} 是**有窗**线程（source=${src || "判不出来"}）。`);
  console.error("  AGENTS.md「往线程里写字·合法通道只有三条」：有窗**只许 queue**，**禁止 exec resume**——");
  console.error("  那是「程序往 app 会读的线程里写正文」，会让它此后每轮 400、永久锁死（已实测 3 次）。");
  console.error("  正确做法：请**老板**在它的窗口里手打/粘一句（通道①），或等它自己起回合。**本工具不替你想办法。**");
  process.exit(4);
}
if (DRY) { console.log(`[dry] 无窗（source=exec）→ 打算 exec resume --thread ${tid}`); process.exit(0); }
console.log("… queue 受理但没起回合 → 改走 resume（**无窗实例**的正常情况，通道③）");
try {
  execFileSync(exe, ["exec", "resume", "--skip-git-repo-check", tid, "-"],
    { input: msg, env, encoding: "utf8", timeout: 600000, stdio: ["pipe", "inherit", "inherit"] });
  console.log(`✓ 已用 resume 叫醒 ${name || tid.slice(0, 8)}`);
} catch (e) {
  console.error("✗ resume 也失败：" + String(e && e.message).slice(0, 200));
  process.exitCode = 1;
}
