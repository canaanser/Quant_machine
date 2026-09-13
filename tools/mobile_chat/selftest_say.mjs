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
// ★ HUB-018 信头规约（老板 2026-09-13 05:1x）：say.mjs 会在正文最前面拼 `【卡号 · 时间戳】`。
//   断言"正文没被吞"时先把信头剥掉再比——信头本身也参与逐字节校验（工具内部已验）。
const CARD = "HUB-018";
// ★ 信头位置：2026-09-13 07:53 起**在正文最后**（原来在最前，污染"正文首行"→ 行首判据全失配）
const HEADER_RE = / 【HUB-018 · \d{4}-\d{2}-\d{2} \d{2}:\d{2}】$/;
const stripHeader = (s) => String(s || "").replace(/ 【[^】]*】$/, "").trim();

function say(args, env) {
  const r = spawnSync(process.execPath, [SAY, ...args], {
    cwd: REPO,
    env: { ...process.env, ...env },
    encoding: "utf8",
  });
  return { code: r.status, out: String(r.stdout || ""), err: String(r.stderr || "") };
}
// 并发版（用于 ⑦ 的"同一分钟两个作者"竞态）
function sayAsync(args, env) {
  return new Promise((res) => {
    const c = spawn(process.execPath, [SAY, ...args], { cwd: REPO, env: { ...process.env, ...env } });
    let o = "";
    let e = "";
    c.stdout.on("data", (d) => (o += d));
    c.stderr.on("data", (d) => (e += d));
    c.on("close", (code) => res({ code, out: o, err: e }));
  });
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
  const r1 = say(["--file", BODY_FILE, "--author", author, "--card", CARD, "--to", "老板"], env);
  ck("① 多行发看板 → 默认拒绝（不许静默丢格式）", r1.code === 2 && /行式存储/.test(r1.err), "exit=" + r1.code);

  // ② 多行发看板 + --flatten → 成功且与"压好的文本"一致
  const r2 = say(["--file", BODY_FILE, "--author", author, "--card", CARD, "--to", "老板", "--flatten", "--json"], env);
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
    stripHeader(boardRec.body) === FLATTENED &&
      HEADER_RE.test(String(boardRec.body || "")) &&
      String(boardRec.body || "").includes("a37bbd9") &&
      String(boardRec.body || "").includes("`x1") &&
      String(boardRec.body || "").includes("${a}") &&
      !String(boardRec.body || "").includes("\u0007") &&
      !String(boardRec.body || "").includes("\u000c"),
    "len=" + String(boardRec.body || "").length
  );

  // ③ 多行发信箱 → 成功且换行原样保留
  const r3 = say(["--file", BODY_FILE, "--author", author, "--card", CARD, "--to", "codex-总监", "--mail", "--json"], env);
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
    stripHeader(mailRec.body) === POISON && String(mailRec.body || "").split("\n").length === 4,
    "lines=" + String(mailRec.body || "").split("\n").length
  );

  // ④ 真源指错 → 必须报错非零退出
  const emptyDir = path.join(ROOT, "empty");
  fs.mkdirSync(emptyDir, { recursive: true });
  const r4 = say(
    ["--file", BODY_FILE, "--author", author, "--card", CARD, "--to", "老板", "--flatten"],
    { ...env, MCHAT_DIALOG_FILE: path.join(emptyDir, "dialog.ndjson") }
  );
  ck("④ 回读找不到落盘记录 → 报错并非零退出（不假装成功）", r4.code === 1 && /失败/.test(r4.err), "exit=" + r4.code);

  // ⑤ 长度闸（--max）：超长直接拒绝，不发送（门铃/回执有"≤200 字"的约定，别靠人肉数）
  const longFile = path.join(ROOT, "long.txt");
  fs.writeFileSync(longFile, "字".repeat(50), "utf8");
  const r5 = say(["--file", longFile, "--author", author, "--card", CARD, "--to", "老板", "--max", "10"], env);
  ck("⑤ 超长正文被 --max 拦住（非零退出 + 报字数）", r5.code === 3 && /超过 --max 10 字/.test(r5.err), "exit=" + r5.code + " " + r5.err.split("\n")[0]);
  const r5b = say(["--file", longFile, "--author", author, "--card", CARD, "--to", "老板", "--max", "200"], env);
  ck("⑤ 长度达标就照常发（没有误杀）", r5b.code === 0 && /回读逐字节一致/.test(r5b.out), "exit=" + r5b.code);

  // ⑥ 信头规约（HUB-018）：不给 --card 直接拒绝；`--card -` = 显式"无卡"，照发
  const r6 = say(["--file", BODY_FILE, "--author", author, "--to", "老板", "--flatten"], env);
  ck("⑥ 缺 --card → 拒绝发送（每封信都要带卡号 + 时间戳）", r6.code === 2 && /--card/.test(r6.err), "exit=" + r6.code);
  const r6b = say(["--file", longFile, "--author", author, "--card", "-", "--to", "老板", "--max", "200"], env);
  ck("⑥ `--card -`（显式无卡）照常发，信头印「无卡」", r6b.code === 0 && /回读逐字节一致/.test(r6b.out), "exit=" + r6b.code);
  const noCardRec = fs
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
    "⑥ 无卡也带时间戳（信头在**最后**：【无卡 · 2026-09-13 0x:xx】）",
    /【无卡 · \d{4}-\d{2}-\d{2} \d{2}:\d{2}】$/.test(String(noCardRec.body || "")),
    JSON.stringify(String(noCardRec.body || "").slice(0, 30))
  );

  // ⑦ **假失败**（codex-修复 2026-09-13 07:06 报的）：同一分钟里**别人发给同一收件人**的信
  //   成了文件最后一行 → 回读如果"按收件人取最后一行"，就拿别人的行来比 → 必然 MISMATCH →
  //   **假失败**（比没校验更危险：线以为没发出去会重发，正好制造重复噪声）。
  //
  //   ⚠️ 端到端造不出**确定性**复现（POST 与回读之间的并发窗口太窄；我先写了并发版用例，
  //      实测**旧代码也绿**——那是摆设，所以改成把**匹配逻辑**单独拎出来做确定性判别）。
  //   夹具：我的那条**被夹在别人两条之间**（最后一行是别人的）→ 旧版必红、新版必绿。
  const probeFile = path.join(ROOT, "verify-probe.ndjson");
  const probeExpect = path.join(ROOT, "verify-probe-expect.txt");
  const MYBODY = "【无卡 · 2026-09-13 07:05】 我的正文（452 字那封）";
  fs.writeFileSync(
    probeFile,
    [
      JSON.stringify({ ts: "2026-09-13 07:05", from: "乙", to: "codex-总监", body: "别人的正文一" }),
      JSON.stringify({ ts: "2026-09-13 07:05", from: "codex-看板编辑", to: "codex-总监", body: MYBODY }),
      JSON.stringify({ ts: "2026-09-13 07:05", from: "乙", to: "codex-总监", body: "别人的正文二（它才是最后一行）" }),
    ].join("\n") + "\n",
    "utf8"
  );
  fs.writeFileSync(probeExpect, MYBODY, "utf8");
  const probe = say(
    ["--verify-probe", probeFile, "--probe-from", "codex-看板编辑", "--probe-to", "codex-总监", "--probe-expect", probeExpect],
    env
  );
  ck(
    "⑦ 回读必须按 **(发件人, 收件人) 找我那条**，不许拿别人写在最后的行来比（假失败根因）",
    probe.code === 0,
    "exit=" + probe.code + " " + String(probe.out || probe.err).trim().slice(0, 110)
  );

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
