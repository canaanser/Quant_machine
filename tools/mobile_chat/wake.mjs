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
 *   ③ **投完验证对方"真起了回合"**（看它自己的 rollout 账本 mtime 有没有前进）；
 *      没起就自动改用 `codex exec resume`（无窗实例 `queue` 叫不醒，见 LESSONS L33）。
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const ROSTER = path.join(ROOT, "outputs", "dialog", "agents.json");
const SESSIONS = path.join(os.homedir(), ".codex", "sessions");

const opt = (f, d = "") => { const i = process.argv.indexOf(f); return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };

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
try { execFileSync(exe, ["queue", "--thread", tid, "--message", msg], { env, encoding: "utf8", timeout: 90000 }); }
catch (e) { code = 1; }

let started = false;
for (let i = 0; i < 8 && code === 0; i++) {
  if (mtime(rollout(tid)) > m0) { started = true; break; }
  try { execFileSync("ping", ["-n", "2", "127.0.0.1"], { stdio: "ignore" }); } catch {}
}
if (started) { console.log(`✓ 已叫醒 ${name || tid.slice(0, 8)}（queue 生效，账本已前进）`); process.exit(0); }

console.log("… queue 受理但没起回合 → 改走 resume（无窗实例的正常情况）");
try {
  execFileSync(exe, ["exec", "resume", "--skip-git-repo-check", tid, "-"],
    { input: msg, env, encoding: "utf8", timeout: 600000, stdio: ["pipe", "inherit", "inherit"] });
  console.log(`✓ 已用 resume 叫醒 ${name || tid.slice(0, 8)}`);
} catch (e) {
  console.error("✗ resume 也失败：" + String(e && e.message).slice(0, 200));
  process.exitCode = 1;
}
