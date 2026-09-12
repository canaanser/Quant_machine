#!/usr/bin/env node
// say.mjs —— **安全的"发一句话"入口**（看板 / 信箱）
//
// 为什么要有它（老板 2026-09-13："你要解决的是怎么不被吞"）：
//   直接在 shell 里拼正文会被各层转义吃掉字符，最典型的是 PowerShell——
//   双引号里的**反引号是转义符**：`a 变成响铃符(BEL)、`f 变成换页(CFF)、`n 变成换行……
//   现场事故：一条交活里的短 hash a37bbd9 被吃成 37bbd9，另一条的分支名
//   feature/... 被吃成 eature/...。这类"被吞"是**静默**的：发出去看不出来，对面照着错信息办事。
//
// 两条纪律合起来才叫"不被吞"：
//   ① **正文只从文件读**——正文文件用补丁/编辑器落盘（字节精确），shell 里只出现路径；
//   ② **发完回读真源逐字节比对**——不一致就报 MISMATCH 并**非零退出**，绝不假装成功。
//
// 用法：
//   node tools/mobile_chat/say.mjs --file run/outbox/msg.txt --author codex-看板编辑 [--to 老板]
//   node tools/mobile_chat/say.mjs --file run/outbox/msg.txt --author codex-看板编辑 --to codex-总监 --mail --wake
// 参数：
//   --file <路径>     必填。正文文件（UTF-8）。会做三件小事：去 BOM / CRLF→LF / 去首尾空白
//                     （与 Hub 的 `body.trim()` 对齐，避免"我发了空格，对面看不见"）。
//   --author <看板名> 必填。你的实名看板名（泛称会被 Hub 拒收）。
//   --to <看板名>     看板模式的收件人（默认 老板）；--mail 模式是收信人（必填）。
//   --mail            投对方信箱（POST /api/mail）而不是发板（POST /api/post）。
//   --wake            仅 --mail：顺手敲门铃（投递成功 ≠ 对方起了回合，见 AGENTS.md）。
//   --dry             只打印正文摘要与 sha256，不发送、不落真源。
//   --json            以 JSON 打印结果（给脚本/自动化用）。
//   --flatten         仅发板：看板是**行式存储**（一条一行），多行正文会被 Hub 压成一行。
//                     默认多行**直接拒绝**（不许静默丢格式）；加这个参数=你明确接受压缩，
//                     工具会先按 Hub 同一口径压好再发、再拿压好的文本去校验。
//   环境变量：MCHAT_BASE（默认取 100.64.75.72:8788）、MCHAT_TOKEN_FILE、MCHAT_MAILBOX_DIR、
//             MCHAT_DIALOG_FILE、MCHAT_WORKSPACE（默认 E:\stockgate\Quant_Alpha_System）。

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";

const WORKSPACE = process.env.MCHAT_WORKSPACE || "E:\\stockgate\\Quant_Alpha_System";
const BASE = process.env.MCHAT_BASE || "http://100.64.75.72:8788";
const TOKEN_FILE = process.env.MCHAT_TOKEN_FILE || path.join(os.homedir(), ".codex", "mobile_chat", "token.txt");
const DIALOG_FILE = process.env.MCHAT_DIALOG_FILE || path.join(WORKSPACE, "outputs", "dialog", "dialog.ndjson");
const MAILBOX_DIR = process.env.MCHAT_MAILBOX_DIR || path.join(WORKSPACE, "outputs", "dialog");

function arg(name, def) {
  const i = process.argv.indexOf(name);
  if (i < 0) return def;
  const v = process.argv[i + 1];
  return v === undefined || v.startsWith("--") ? true : v;
}
const has = (name) => process.argv.includes(name);

const file = arg("--file", "");
const author = arg("--author", "");
const to = arg("--to", "");
const useMail = has("--mail");
const wake = has("--wake");
const dry = has("--dry");
const asJson = has("--json");
const flatten = has("--flatten");

if (!file || !author || (useMail && !to)) {
  process.stderr.write(
    "用法：node tools/mobile_chat/say.mjs --file <正文文件> --author <看板名> [--to <看板名>] [--mail] [--wake] [--dry]\n"
  );
  process.exit(2);
}

// 正文：只从文件读，并做与 Hub 一致的归（去 BOM / CRLF→LF / 去首尾空白）
const raw = fs.readFileSync(file, "utf8");
const body = raw.replace(/^\uFEFF/, "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
const sha = (s) => crypto.createHash("sha256").update(s, "utf8").digest("hex");
if (!body) {
  process.stderr.write("空正文，不发。\n");
  process.exit(2);
}
// 看板行式存储：Hub 的 appendBoardLine 会做 `\s*\n\s*` → " "。这里对齐同一口径，
// 免得"我发的是多行、落盘变成一行"被当成别人改了内容（2026-09-13 首次联调就撞上）。
const FLATTEN = (s) => s.replace(/\s*\n\s*/g, " ").trim();
let send = body;
if (!useMail) {
  if (/\n/.test(body) && !flatten) {
    process.stderr.write(
      "拒绝发送：看板是行式存储，多行正文会被压成一行（换行 → 空格）。\n" +
        "两种改法：① 要保留多行 → 改成 --mail（投它信箱，原样保留）；\n" +
        "          ② 明确接受压缩 → 加 --flatten（工具会先压好再发、再按压好的文本校验）。\n"
    );
    process.exit(2);
  }
  if (/\n/.test(body)) {
    send = FLATTEN(body);
    process.stderr.write("提示：已按看板口径压成一行（" + body.split("\n").length + " 行 → 1 行，sha256 用压好的算）。\n");
  }
}

function readToken() {
  try {
    return fs.readFileSync(TOKEN_FILE, "utf8").trim();
  } catch {
    return "";
  }
}

// 回读真源：在最近 N 条记录里找**正文完全相等**的那条（不看"像不像"，只看逐字节）
function verify(filePath, pick, expected) {
  let rows = [];
  try {
    rows = fs.readFileSync(filePath, "utf8").split("\n").filter((l) => l.trim());
  } catch (e) {
    return { ok: false, why: "真源读不到：" + e.message };
  }
  const tail = rows.slice(-40);
  for (let i = tail.length - 1; i >= 0; i--) {
    let rec = null;
    try {
      rec = JSON.parse(tail[i]);
    } catch {
      continue;
    }
    if (!pick(rec)) continue;
    if (String(rec.body || "") === expected) return { ok: true, ts: rec.ts, id: rec.id || "" };
    return {
      ok: false,
      why: "落盘正文与输入不一致（被吞/被改）",
      got: String(rec.body || ""),
      ts: rec.ts,
    };
  }
  return { ok: false, why: "真源里没找到刚发的这条（可能发失败了）" };
}

function firstDiff(a, b) {
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i++) {
    if (a[i] !== b[i]) {
      const cp = (s) => (s[i] === undefined ? "-" : "U+" + s.codePointAt(i).toString(16).toUpperCase().padStart(4, "0"));
      return { at: i, want: cp(a), got: cp(b), ctx: JSON.stringify(a.slice(Math.max(0, i - 12), i + 12)) };
    }
  }
  return null;
}

const out = { ok: false, mode: useMail ? "mail" : "post", author, to: to || "老板", sha256: sha(send), len: [...send].length };
if (dry) {
  out.ok = true;
  out.dry = true;
  process.stdout.write(
    asJson
      ? JSON.stringify(out) + "\n"
      : "dry：正文 " + out.len + " 字 · sha256=" + out.sha256.slice(0, 16) + "…\n" + send + "\n"
  );
  process.exit(0);
}

const token = readToken();
const url = BASE + (useMail ? "/api/mail" : "/api/post");
const payload = useMail
  ? { to, from: author, body: send, wake: wake ? true : undefined }
  : { author, target: to || "老板", body: send };

const res = await fetch(url, {
  method: "POST",
  headers: { "Content-Type": "application/json", "x-mchat-token": token },
  body: JSON.stringify(payload),
}).catch((e) => ({ _err: e }));

if (!res || res._err) {
  out.error = String((res && res._err && res._err.message) || "网络失败");
} else {
  const j = await res.json().catch(() => ({}));
  out.status = res.status;
  out.reply = j;
  if (!res.ok) out.error = j.error || ("HTTP " + res.status);
  else {
    // ★ 关键一步：回读真源，逐字节校验
    const v = useMail
      ? verify(path.join(MAILBOX_DIR, j.mailbox || ""), (r) => String(r.to || "") === String(j.to || to), send)
      : verify(DIALOG_FILE, (r) => String(r.from || "") === author && String(r.to || "") === String(to || "老板"), send);
    out.verify = v;
    out.ok = !!v.ok;
    if (!v.ok) {
      out.error = v.why;
      const d = firstDiff(send, v.got || "");
      if (d) out.diff = d;
    } else if (useMail) {
      out.woke = !!j.woke;
      out.deduped = !!j.deduped;
    }
  }
}

if (asJson) {
  process.stdout.write(JSON.stringify(out) + "\n");
} else if (out.ok) {
  process.stdout.write(
    "OK " + out.mode + " → " + out.to + " · " + out.len + " 字 · sha256=" + out.sha256.slice(0, 16) + "…" +
      (out.mode === "mail" ? " · 门铃=" + (out.woke ? "响" : "未响（已排补投）") : "") +
      " · 回读逐字节一致\n"
  );
} else {
  process.stderr.write("失败：" + (out.error || "未知") + "\n");
  if (out.diff) {
    process.stderr.write(
      "首个差异位置 " + out.diff.at + "：输入 " + out.diff.want + " / 落盘 " + out.diff.got + "\n" +
        "上下文（落盘）：" + out.diff.ctx + "\n"
    );
  }
  if (out.verify && out.verify.got !== undefined) {
    process.stderr.write("输入长度=" + [...send].length + " 落盘长度=" + [...String(out.verify.got)].length + "\n");
  }
}
process.exit(out.ok ? 0 : 1);
