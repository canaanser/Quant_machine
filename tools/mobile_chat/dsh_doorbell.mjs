#!/usr/bin/env node
/**
 * PLT-007 事件注入 / 通道层：DSH 门铃（Windows 侧实现，不依赖 WSL）
 *
 * 作用：把一条事件注入 DSH 的 GUI 会话（默认 `dsh-老员工`），并**验证它真的起了回合**。
 * 这是"线 → DSH"的唯一机器通道（DSH 无 threadId，小工按设计跳过它）。
 *
 * 用法：
 *   node tools/mobile_chat/dsh_doorbell.mjs --file <正文文件> [--session <会话id>]
 *        [--cookie <cookie文件>] [--max-per-day N] [--dry] [--no-verify] [--list]
 *
 * 守卫（与卡面 PLT-007 §二 对齐）：
 *   · requestId 一信一号；同内容 10 分钟内不重发（state 记账）
 *   · 401 → 用启动日志的 token 重换 cookie 后重试一次，间隔 ≥2s；仍失败 → 兜底
 *   · 日限流（默认 20/天，按本地日期）
 *   · 失败兜底：回投 `outputs/dialog/pending_dsh-main.ndjson` + 打印告警（--alert-board 才上板）
 *   · 验收判据：投递后**对方 updatedAt 必须变化**，只看 accepted 不算过
 */

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");

// ★ 本机死代理坑（AR-001 有记载）：环境里挂着 http_proxy=127.0.0.1:7890（已死），
// Node 的 fetch 会照用 → 请求挂死到超时（实测 "This operation was aborted"）。
// 门铃只打 127.0.0.1，直接摘掉代理变量。
for (const k of ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]) {
  delete process.env[k];
}

const DEFAULTS = {
  base: process.env.DSH_DOORBELL_BASE || "http://127.0.0.1:3080",
  session: process.env.DSH_DOORBELL_SESSION || "session-4258a4fe-4dbd-49f7-a12b-67a5fa153417",
  cookie: process.env.DSH_DOORBELL_COOKIE || "C:\\Users\\Administrator\\.dsh-sentinel\\cookie.txt",
  weblog: process.env.DSH_DOORBELL_WEBLOG || "\\\\wsl.localhost\\Ubuntu-24.04\\home\\lgy\\.dsh-web.log",
  state: process.env.DSH_DOORBELL_STATE || path.join(REPO, "outputs", "dialog", "doorbell_state.json"),
  mailbox: process.env.DSH_DOORBELL_MAILBOX || path.join(REPO, "outputs", "dialog", "pending_dsh-main.ndjson"),
  maxPerDay: 20,
};

function arg(name, fallback = "") {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}
const has = (name) => process.argv.includes(name);

const fail = (msg) => {
  console.error("拒绝：" + msg);
  process.exit(2);
};

function readState() {
  try {
    return JSON.parse(fs.readFileSync(DEFAULTS.state, "utf8"));
  } catch {
    return { day: "", count: 0, sent: {} };
  }
}

function writeState(state) {
  fs.mkdirSync(path.dirname(DEFAULTS.state), { recursive: true });
  fs.writeFileSync(DEFAULTS.state, JSON.stringify(state, null, 2), "utf8");
}

/** 本地日期（不要用 toISOString：那是 UTC，会把日限流记到前一天）。 */
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const sha = (s) => crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function http(url, opts = {}, timeoutMs = 15000) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...opts, signal: ctl.signal });
    const text = await res.text();
    return { status: res.status, headers: res.headers, text };
  } catch (e) {
    return { status: 0, headers: new Map(), text: String(e && e.message) };
  } finally {
    clearTimeout(timer);
  }
}

function readCookie() {
  try {
    return fs.readFileSync(DEFAULTS.cookie, "utf8").trim();
  } catch {
    return "";
  }
}

/** 401 兜底：从 dsh web 启动日志抓 token 重换 cookie（日志可能是旧的，失败要留痕）。 */
async function remintCookie() {
  let log = "";
  try {
    log = fs.readFileSync(DEFAULTS.weblog, "utf8");
  } catch (e) {
    return { ok: false, why: "读不到启动日志：" + String(e.message).slice(0, 80) };
  }
  const found = log.match(/token=([A-Za-z0-9_-]+)/g);
  if (!found || !found.length) return { ok: false, why: "启动日志里没有 token" };
  const token = found[found.length - 1].slice(6);
  const res = await http(`${DEFAULTS.base}/?token=${token}`, { method: "GET", redirect: "manual" });
  const setCookie = res.headers.get ? res.headers.get("set-cookie") : null;
  if (!setCookie) {
    return { ok: false, why: `换 cookie 失败（HTTP ${res.status}，多半是日志里的 token 已失效）` };
  }
  const pair = setCookie.split(";")[0].trim();
  try {
    fs.mkdirSync(path.dirname(DEFAULTS.cookie), { recursive: true });
    fs.writeFileSync(DEFAULTS.cookie, pair, "utf8");
  } catch (e) {
    return { ok: false, why: "cookie 写不回：" + String(e.message).slice(0, 60) };
  }
  return { ok: true };
}

/** 注入一次；返回 { ok, status, accepted, why }。 */
async function inject(text, sessionId, requestId) {
  const body = JSON.stringify({
    type: "client-request",
    rpcId: crypto.randomUUID(),
    method: "session/prompt",
    payload: {
      args: {
        request: {
          sessionId,
          requestId,
          mode: "queue",
          content: [{ type: "text", text }],
        },
      },
    },
  });
  const call = async () =>
    http(`${DEFAULTS.base}/api/session/prompt`, {
      method: "POST",
      headers: { "content-type": "application/json", cookie: readCookie() },
      body,
    });

  let res = await call();
  if (res.status === 401) {
    const fixed = await remintCookie();
    if (!fixed.ok) return { ok: false, status: 401, why: fixed.why };
    await sleep(2000); // 守卫：重试间隔 ≥2s
    res = await call();
  }
  if (res.status !== 200) return { ok: false, status: res.status, why: res.text.slice(0, 120) };
  let parsed;
  try {
    parsed = JSON.parse(res.text);
  } catch {
    return { ok: false, status: 200, why: "返回不是 JSON" };
  }
  const ok = Boolean(parsed?.result?.ok);
  return { ok, status: 200, why: ok ? "" : JSON.stringify(parsed.result || {}).slice(0, 120) };
}

/** 验收判据：拿 session/list 看该会话 updatedAt。 */
async function sessionUpdatedAt(sessionId) {
  const res = await http(`${DEFAULTS.base}/api/session/list`, {
    method: "POST",
    headers: { "content-type": "application/json", cookie: readCookie() },
    body: JSON.stringify({
      type: "client-request",
      rpcId: crypto.randomUUID(),
      method: "session/list",
      payload: { args: { _request: {} } },
    }),
  });
  if (res.status !== 200) return null;
  try {
    const items = JSON.parse(res.text)?.result?.value?.items || [];
    const hit = items.find((x) => x.sessionId === sessionId);
    return hit ? hit.updatedAt : null;
  } catch {
    return null;
  }
}

function fallback(kind, text, why) {
  const line = JSON.stringify({
    ts: new Date().toISOString().replace("T", " ").slice(0, 16),
    from: "codex-唤醒通道",
    to: "dsh-老员工",
    body: `【门铃失败·兜底·${kind}】${why}\n原文：${text.slice(0, 300)}`,
  });
  fs.mkdirSync(path.dirname(DEFAULTS.mailbox), { recursive: true });
  fs.appendFileSync(DEFAULTS.mailbox, line + "\n", "utf8");
  console.error(`⚠️  门铃失败已兜底回投 ${path.relative(REPO, DEFAULTS.mailbox)}（${why}）`);
  if (has("--alert-board")) {
    const note = path.join(REPO, "outputs", "dialog", "doorbell_alert.txt");
    fs.writeFileSync(note, `【故障·门铃】${kind}：${why}\n已兜底回投 pending_dsh-main.ndjson。`, "utf8");
    spawnSync(process.execPath, [
      path.join(HERE, "say.mjs"), "--file", note, "--author", "codex-唤醒通道",
      "--card", "PLT-007", "--to", "老板", "--flatten", "--max", "200",
    ], { stdio: "inherit" });
  }
}

async function main() {
  if (has("--list")) {
    const res = await http(`${DEFAULTS.base}/api/session/list`, {
      method: "POST",
      headers: { "content-type": "application/json", cookie: readCookie() },
      body: JSON.stringify({
        type: "client-request", rpcId: crypto.randomUUID(), method: "session/list",
        payload: { args: { _request: {} } },
      }),
    });
    const items = JSON.parse(res.text || "{}")?.result?.value?.items || [];
    for (const it of items.slice(0, 20)) {
      console.log(`${it.sessionId}  ${it.cwd}  ${it.projections?.values?.title || ""}`);
    }
    return 0;
  }

  const file = arg("--file");
  if (!file) fail("缺 --file（正文文件；正文不拼进命令行）");
  let text;
  try {
    text = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "").trim();
  } catch (e) {
    fail("读不到正文文件：" + e.message);
  }
  if (!text) fail("正文为空");

  const sessionId = arg("--session", DEFAULTS.session);
  const maxPerDay = Number(arg("--max-per-day", String(DEFAULTS.maxPerDay))) || DEFAULTS.maxPerDay;
  const state = readState();
  if (state.day !== today()) {
    state.day = today();
    state.count = 0;
  }

  const hash = sha(text);
  const lastAt = Number(state.sent?.[hash] || 0);
  const tenMin = 10 * 60 * 1000;
  if (lastAt && Date.now() - lastAt < tenMin && !has("--force")) {
    console.log(`跳过：同内容 10 分钟内已发过（hash=${hash}）`);
    return 0;
  }
  if (state.count >= maxPerDay) {
    console.log(`跳过：今日已达上限 ${maxPerDay}（state.day=${state.day}）`);
    return 0;
  }
  if (has("--dry")) {
    console.log(`[dry] 将注入 session=${sessionId} 字数=${[...text].length} hash=${hash}`);
    return 0;
  }

  const before = has("--no-verify") ? null : await sessionUpdatedAt(sessionId);
  const requestId = crypto.randomUUID();
  const result = await inject(text, sessionId, requestId);

  if (!result.ok) {
    state.count += 1;
    state.sent[hash] = Date.now();
    writeState(state);
    fallback("inject", text, `HTTP ${result.status} ${result.why}`);
    return 1;
  }

  state.count += 1;
  state.sent[hash] = Date.now();
  writeState(state);
  console.log(`注入 accepted（session=${sessionId}，requestId=${requestId}，今日 ${state.count}/${maxPerDay}）`);

  if (has("--no-verify")) return 0;
  // 验收：等它真起回合（updatedAt 变化），最多等 30 秒
  for (let i = 0; i < 15; i += 1) {
    await sleep(2000);
    const now = await sessionUpdatedAt(sessionId);
    if (now && now !== before) {
      console.log(`✅ 已验证：对方起了回合（updatedAt ${before} → ${now}）`);
      return 0;
    }
  }
  console.log("⚠️  投递成功但 30 秒内未见 updatedAt 变化——按卡面口径这不算过，请查会话是否被占用");
  return 3;
}

// 用 exitCode 自然退出：直接 process.exit() 在 Windows/Node 里会撞 teardown（实测退出码 0xC0000409）。
main().then(
  (code) => {
    process.exitCode = code;
  },
  (err) => {
    console.error("门铃内部错误：" + ((err && err.stack) || err));
    process.exitCode = 4;
  },
);
