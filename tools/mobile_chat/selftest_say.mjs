#!/usr/bin/env node
// say.mjs 的自测：证明"发出去的正文不会被静默改掉"，且改不动就报错。
//
// 做法：起一个**完全隔离**的 Hub 实例（随机端口 + 临时目录），用一份"毒文本"
// （反引号 / $ / ${} / 中文 / 短 hash）跑四种情形：
//   ① 多行发看板、不给 --flatten → 必须**拒绝**（exit 2）
//   ② 多行发看板 + --flatten      → 必须成功，且回读与"压好的文本"逐字节一致
//   ③ 多行发信箱                  → 必须成功，且**换行原样保留**
//   ④ 真源指错（空目录）          → 必须**报错非零退出**（不许假装成功）
//
// 用法：node tools/mobile_chat/selftest_say.mjs [--tmp <目录>]

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "..", "..");
const SAY = path.join(__dirname, "say.mjs");
const BOARD = path.join(__dirname, "board.mjs");
const PORT = 8800 + Math.floor(Math.random() * 90);

const tmpIdx = process.argv.indexOf("--tmp");
const base = path.resolve(
  (tmpIdx >= 0 && process.argv[tmpIdx + 1]) || process.env.SELFTEST_TMP || path.join(REPO, "run", "selftest-say")
);
function longPath(p) {
  try {
    fs.mkdirSync(p, { recursive: true });
    return fs.realpathSync.native(p);
  } catch {
    return p;
  }
}
try {
  const d = path.dirname(base);
  fs.mkdirSync(d, { recursive: true });
  const gi = path.join(d, ".gitignore");
  if (!fs.existsSync(gi)) fs.writeFileSync(gi, "*\n", "utf8");
} catch {}
const ROOT = path.join(longPath(base), "say" + Date.now().toString(36).slice(-4));
const dirs = { data: path.join(ROOT, "data"), mailbox: path.join(ROOT, "mailbox") };
const DIALOG = path.join(dirs.data, "dialog.ndjson");
const BODY_FILE = path.join(ROOT, "poison.txt");

const results = [];
const ck = (name, ok, detail) => {
  results.push(ok);
  process.stdout.write((ok ? "  PASS  " : "  FAIL  ") + name + (detail ? "  -> " + detail : "") + "\n");
};

const POISON = [
  "【自测·安全发送】短 hash a37bbd9 ｜ 反引号 `x1` ｜ 美元 $HOME 与 ${a} ｜ 引号 \"双\" 和 '单'",
  "第二行：`a37bbd9`——PowerShell 双引号里会把 `a 吃成响铃符（BEL）",
  "第三行：`feature/hub-carry-layer`（`f 会变成换页符 CFF）",
  "第四行：中文「」、破折号——、emoji ✅⚠️",
].join("\n");
const FLATTENED = POISON.replace(/\s*\n\s*/g, " ").trim();

function say(args, env) {
  const r = spawnSync(process.execPath, [SAY, ...args], {
    cwd: REPO,
    env: { ...process.env, ...env },
    encoding: "utf8",
  });
  return { code: r.status, out: String(r.stdout || ""), err: String(r.stderr || "") };
}

let child = null;
let childLog = "";
let code = 1;
try {
  fs.mkdirSync(dirs.data, { recursive: true });
  fs.mkdirSync(dirs.mailbox, { recursive: true });
  fs.writeFileSync(BODY_FILE, POISON, "utf8");
  // 让 Hub 认得"作者"这个署名：拿真仓库的名册抄一份进隔离目录（只读复制）
  try {
    fs.copyFileSync(path.join(REPO, "outputs", "dialog", "agents.json"), path.join(dirs.data, "agents.json"));
  } catch {}

  child = spawn(process.execPath, [BOARD], {
    cwd: __dirname,
    env: {
      ...process.env,
      MCHAT_HOST: "127.0.0.1",
      BOARD_PORT: String(PORT),
      MCHAT_DATA: dirs.data,
      MCHAT_MAILBOX_DIR: dirs.mailbox,
      MCHAT_DIALOG_FILE: DIALOG,
      MCHAT_AGENTS_FILE: path.join(dirs.data, "agents.json"),
      MCHAT_BOARD_FILE: path.join(ROOT, "COMMS_BOARD.md"),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (d) => (childLog += d));
  child.stderr.on("data", (d) => (childLog += d));

  let up = false;
  for (let i = 0; i < 40 && !up; i++) {
    await new Promise((r) => setTimeout(r, 500));
    try {
      const r = await fetch("http://127.0.0.1:" + PORT + "/api/ping");
      up = r.ok;
    } catch {}
  }
  ck("隔离实例起来了（随机端口 + 临时目录）", up, "port=" + PORT + " tmp=" + ROOT);

  const env = {
    MCHAT_BASE: "http://127.0.0.1:" + PORT,
    MCHAT_TOKEN_FILE: path.join(dirs.data, "token.txt"),
    MCHAT_MAILBOX_DIR: dirs.mailbox,
    MCHAT_DIALOG_FILE: DIALOG,
    MCHAT_WORKSPACE: REPO,
  };
  const author = "codex-看板编辑";

  // ① 多行发看板、不给 --flatten → 拒绝
  const r1 = say(["--file", BODY_FILE, "--author", author, "--to", "老板"], env);
  ck("① 多行发看板 → 默认拒绝（不许静默丢格式）", r1.code === 2 && /行式存储/.test(r1.err), "exit=" + r1.code);

  // ② 多行发看板 + --flatten → 成功且与"压好的文本"一致
  const r2 = say(["--file", BODY_FILE, "--author", author, "--to", "老板", "--flatten", "--json"], env);
  let j2 = {};
  try {
    j2 = JSON.parse(r2.out);
  } catch {}
  ck(
    "② 多行 + --flatten 发看板 → 成功且回读逐字节一致",
    r2.code === 0 && j2.ok === true && j2.verify && j2.verify.ok === true,
    "exit=" + r2.code + " " + (j2.error || "")
  );
  const boardRec = fs
    .readFileSync(DIALOG, "utf8")
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => {
      try {
        return JSON.parse(l);
      } catch {
        return null;
      }
    })
    .filter(Boolean)
    .filter((r) => String(r.from) === author)
    .pop() || {};
  ck(
    "② 落盘正文 = 压好后的原文（毒字符原样活着，换行按看板口径变空格）",
    String(boardRec.body || "") === FLATTENED &&
      String(boardRec.body || "").includes("a37bbd9") &&
      String(boardRec.body || "").includes("`x1") &&
      String(boardRec.body || "").includes("${a}") &&
      !String(boardRec.body || "").includes("\u0007") &&
      !String(boardRec.body || "").includes("\u000c"),
    "len=" + String(boardRec.body || "").length
  );

  // ③ 多行发信箱 → 成功且换行原样保留
  const r3 = say(["--file", BODY_FILE, "--author", author, "--to", "codex-总监", "--mail", "--json"], env);
  let j3 = {};
  try {
    j3 = JSON.parse(r3.out);
  } catch {}
  ck(
    "③ 多行发信箱 → 成功且回读逐字节一致",
    r3.code === 0 && j3.ok === true && j3.verify && j3.verify.ok === true,
    "exit=" + r3.code + " " + (j3.error || "")
  );
  const mailFile = path.join(dirs.mailbox, "pending_codex-director.ndjson");
  let mailRec = {};
  try {
    mailRec = JSON.parse(fs.readFileSync(mailFile, "utf8").split("\n").filter((l) => l.trim()).pop());
  } catch {}
  ck(
    "③ 信箱里换行原样保留（4 行）",
    String(mailRec.body || "") === POISON && String(mailRec.body || "").split("\n").length === 4,
    "lines=" + String(mailRec.body || "").split("\n").length
  );

  // ④ 真源指错 → 必须报错非零退出
  const emptyDir = path.join(ROOT, "empty");
  fs.mkdirSync(emptyDir, { recursive: true });
  const r4 = say(
    ["--file", BODY_FILE, "--author", author, "--to", "老板", "--flatten"],
    { ...env, MCHAT_DIALOG_FILE: path.join(emptyDir, "dialog.ndjson") }
  );
  ck("④ 回读找不到落盘记录 → 报错并非零退出（不假装成功）", r4.code === 1 && /失败/.test(r4.err), "exit=" + r4.code);

  const failed = results.filter((x) => !x).length;
  process.stdout.write("\nsay 自测结果：" + (results.length - failed) + "/" + results.length + " 通过\n");
  if (failed && childLog) process.stdout.write("--- 实例日志尾部 ---\n" + childLog.slice(-600) + "\n");
  code = failed ? 1 : 0;
} catch (e) {
  process.stdout.write("say 自测异常：" + (e && e.stack) + "\n");
  if (childLog) process.stdout.write("--- 实例日志尾部 ---\n" + childLog.slice(-800) + "\n");
  code = 1;
} finally {
  try {
    if (child) child.kill();
  } catch {}
  try {
    fs.rmSync(ROOT, { recursive: true, force: true });
  } catch {}
}
process.exit(code);
