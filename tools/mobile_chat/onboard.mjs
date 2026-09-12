#!/usr/bin/env node
// onboard.mjs —— 入职登记（HUB-001）：把一条**新来的线**办成正式员工。
//
// 为什么要有它（老板 2026-09-13："你帮修复 bug，走个员工流程吧"）：
//   新窗口（对话框）此前**没有入职路径**——`/api/bind` 只能在已入册的名字上换绑，
//   于是新线既不能被派活、也不能被信箱/门铃叫醒，只能靠人在对话里喊一声。
//   本工具把"入职"做成一条命令：发牌（看板名 + 工号）→ 绑会话 → 建档 → 留痕 → **当场自检**（投信 + 敲门铃）。
//
// 三条硬规矩（与 Hub 的 POST /api/onboard 完全一致，这里是同一条流水线）：
//   ① **工号永不复用**：在册 slug / `slugAliases` 历史工号 / 退役条目，撞了就拒；
//   ② **一个会话只属于一条线**：threadId 已被别人绑 → 拒，并指出是谁；
//   ③ **必须写清批准人**：入职=发牌，只有老板能拍板（红线），接口不接受没批准人的登记。
//
// 用法：
//   node tools/mobile_chat/onboard.mjs --name codex-修复 --slug codex-fix ^
//        --thread 01a08d59-9526-7b73-962e-84595b428be6 ^
//        --by codex-看板编辑 --approval "老板 2026-09-13 01:4x 口述" ^
//        [--title "修复线"] [--note "职责：恢复受损的对话框/线程"] [--no-ring] [--dry]

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "..", "..");
const WORKSPACE = process.env.MCHAT_WORKSPACE || REPO;
const BASE = process.env.MCHAT_BASE || "http://100.64.75.72:8788";
const TOKEN_FILE = process.env.MCHAT_TOKEN_FILE || path.join(os.homedir(), ".codex", "mobile_chat", "token.txt");
const STATE_DIR = process.env.MCHAT_STATE_DIR || process.env.MCHAT_MAILBOX_DIR || path.join(WORKSPACE, "outputs", "dialog");
const AGENTS_FILE = process.env.MCHAT_AGENTS_FILE || path.join(STATE_DIR, "agents.json");

const arg = (n, d) => {
  const i = process.argv.indexOf(n);
  if (i < 0) return d;
  const v = process.argv[i + 1];
  return v === undefined || v.startsWith("--") ? true : v;
};
const has = (n) => process.argv.includes(n);

const name = String(arg("--name", "")).trim().replace(/^@/, "");
const slug = String(arg("--slug", "")).trim().toLowerCase();
const threadId = String(arg("--thread", "")).trim();
const by = String(arg("--by", "")).trim().replace(/^@/, "");
const approval = String(arg("--approval", "")).trim();
const title = String(arg("--title", "")).trim();
const note = String(arg("--note", "")).trim();
const level = String(arg("--level", "")).trim();
const dry = has("--dry");
const ring = !has("--no-ring");

if (!name || !slug || !by || !approval) {
  process.stderr.write(
    "用法：node tools/mobile_chat/onboard.mjs --name <看板名> --slug <工号> --by <办事的看板名> --approval \"<谁批的>\" [--thread <会话id>] [--title …] [--note …] [--dry] [--no-ring]\n"
  );
  process.exit(2);
}

const token = (() => {
  try {
    return fs.readFileSync(TOKEN_FILE, "utf8").trim();
  } catch {
    return "";
  }
})();
const post = (url, body) =>
  fetch(BASE + url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-mchat-token": token },
    body: JSON.stringify(body),
  }).then(async (r) => ({ status: r.status, body: await r.json().catch(() => ({})) }));

const payload = { name, slug, by, approval, ...(threadId ? { threadId } : {}), ...(title ? { title } : {}), ...(note ? { note } : {}), ...(level ? { level } : {}) };

if (dry) {
  process.stdout.write("dry 预览：\n" + JSON.stringify(payload, null, 2) + "\n");
  process.exit(0);
}

// ── 第一步：优先走 Hub 的入职口（正式路径） ─────────────────────────────────
let registered = null;
let via = "api";
const r1 = await post("/api/onboard", payload).catch((e) => ({ status: 0, body: { error: String(e.message) } }));
if (r1.status === 200 && r1.body.ok) {
  registered = r1.body;
} else if ([400, 409].includes(r1.status)) {
  // 业务拒绝（重名/工号撞/会话被占/缺批准人）→ 直接停，不绕
  process.stderr.write("入职被拒（" + r1.status + "）：" + (r1.body.error || "") + "\n" + (r1.body.hint ? "提示：" + r1.body.hint + "\n" : ""));
  process.exit(1);
} else if ([404, 405, 0, 500].includes(r1.status)) {
  // 老 Hub 还没有这个口（或网络抖动）→ **安全直写回退**：同一套校验 + 原子替换 + mtime 校验
  via = "safe-write";
  const statKey = (p) => {
    try {
      const s = fs.statSync(p);
      return s.mtimeMs + ":" + s.size;
    } catch {
      return "none";
    }
  };
  const before = statKey(AGENTS_FILE);
  let cfg = {};
  try {
    cfg = JSON.parse(fs.readFileSync(AGENTS_FILE, "utf8"));
  } catch (e) {
    process.stderr.write("读不到名册：" + AGENTS_FILE + "（" + e.message + "）\n");
    process.exit(1);
  }
  const agents = cfg.agents || {};
  const names = Object.keys(agents);
  const norm = (v) => String(v || "").toLowerCase();
  const GENERIC = ["codex", "dsh", "ds h", "deepseek", "助手", "agent", "ai"];
  if (!names.some((n) => norm(n) === norm(by))) {
    process.stderr.write("by 不是注册看板名：" + by + "\n");
    process.exit(1);
  }
  if (GENERIC.includes(norm(name))) {
    process.stderr.write("名字不能是泛称：" + name + "\n");
    process.exit(1);
  }
  if (names.some((n) => norm(n) === norm(name))) {
    process.stderr.write("这个名字已注册：" + name + "（换绑请用 POST /api/bind）\n");
    process.exit(1);
  }
  if (!/^[a-z0-9][a-z0-9-]{1,30}$/.test(slug)) {
    process.stderr.write("工号格式不对：" + slug + "\n");
    process.exit(1);
  }
  const holder = Object.entries(agents).find(([, m]) => norm((m || {}).slug) === slug);
  if (holder) {
    process.stderr.write("工号已被占用：" + slug + "（现役：" + holder[0] + "）\n");
    process.exit(1);
  }
  const aliasKey = Object.keys(cfg.slugAliases || {}).find((k) => norm(k) === slug);
  if (aliasKey) {
    process.stderr.write("工号已退役、永不复用：" + slug + "（历史岗位：" + cfg.slugAliases[aliasKey] + "）\n");
    process.exit(1);
  }
  if (threadId) {
    if (!/^[0-9a-fA-F-]{36}$/.test(threadId)) {
      process.stderr.write("threadId 格式不对（要 UUID）\n");
      process.exit(1);
    }
    const used = Object.entries(agents).find(([, m]) => String((m || {}).threadId || "") === threadId);
    if (used) {
      process.stderr.write("这个会话已经绑在别的线上：" + used[0] + "\n");
      process.exit(1);
    }
  }
  agents[name] = {
    label: name,
    title: title || "新入职",
    slug,
    workspace: WORKSPACE,
    status: threadId ? "active" : "unknown",
    ...(threadId ? { threadId } : {}),
    ...(level ? { level } : {}),
    duty: false,
    note: "入职登记（" + new Date().toISOString().slice(0, 16).replace("T", " ") + "，by " + by + "，批准：" + approval.slice(0, 60) + "）" + (note ? "；" + note : ""),
  };
  cfg.agents = agents;
  try {
    fs.copyFileSync(AGENTS_FILE, AGENTS_FILE + ".bak-onboard");
  } catch {}
  const tmpf = AGENTS_FILE + ".tmp-onboard-" + Date.now();
  fs.writeFileSync(tmpf, JSON.stringify(cfg, null, 2) + "\n", "utf8");
  if (statKey(AGENTS_FILE) !== before) {
    try {
      fs.unlinkSync(tmpf);
    } catch {}
    process.stderr.write("名册正被其他进程修改（写前写后 stat 不一致）→ 本次未写入，请重试\n");
    process.exit(1);
  }
  fs.renameSync(tmpf, AGENTS_FILE);
  registered = { ok: true, name, slug, threadId: threadId || null, by };
}

if (!registered) {
  process.stderr.write("入职失败：HTTP " + r1.status + " " + JSON.stringify(r1.body) + "\n");
  process.exit(1);
}

// ── 第二步：留痕（看板一行，署名是**办事的人**，不是被办的人） ───────────────
const boardLine =
  "【入职登记 · " + by + "】给 **" + name + "** 办了入职（批准：" + approval + "）：工号 " + slug +
  (threadId ? "，会话 " + threadId.slice(0, 8) + "…" : "，未绑会话") + (title ? "，岗位 " + title : "") + "。";
if (via === "safe-write") {
  // 老 Hub 的 /api/onboard 还不存在时，看板行也走普通发板口（署名=办事人，可审计）
  await post("/api/post", { author: by, target: "老板", body: boardLine }).catch(() => {});
}

// ── 第三步：当场自检——入册后必须**能被投信、能被叫醒**（不然"流程"是空的） ──
let ringInfo = "未验证（--no-ring）";
if (ring) {
  const hello =
    "【入职通知 · " + by + "】你是 **" + name + "**（工号 " + slug + "，岗位 " + (title || "新入职") +
    "）。从这条起，你在看板上的署名就是这个名字；派活会投到你这个信箱、叫醒走门铃。请回看板一行确认在岗。";
  const r = await post("/api/mail", { to: name, from: by, body: hello, wake: true }).catch((e) => ({ status: 0, body: { error: String(e.message) } }));
  ringInfo = r.status === 200 ? "投信 OK · 门铃" + (r.body.woke ? "响" : "未响（已排补投）") : "投信失败：" + JSON.stringify(r.body);
}

process.stdout.write(
  "入职完成（通道=" + via + "）：" + name + " · 工号 " + slug + (threadId ? " · 会话 " + threadId.slice(0, 8) + "…" : "") +
    "\n自检：" + ringInfo + "\n"
);
