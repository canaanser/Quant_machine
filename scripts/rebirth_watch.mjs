#!/usr/bin/env node
/**
 * rebirth_watch —— 把「该不该重生」从**靠人想起来**变成**测出来**（老板 2026-09-13 09:3x 交办）。
 *
 * 数据只从**真源**取，不猜：
 *   · 名册 `outputs/dialog/agents.json`（每条线的 `threadId` = 它**当前实例**）
 *   · rollout 账本 `~/.codex/sessions` 下的 `rollout-*.jsonl`（平台自己记的）：
 *       - `type=compacted`         → **压缩次数**
 *       - `type=token_usage_record` → `payload.usage.input_tokens` 累加 = **累计输入**
 *       - `type=turn_context`       → `payload.turn_id` 去重计数 = **轮数**
 * 只读：本脚本**不改** rollout、不改名册、**不触发重生**（老板边界：只报、不动）。
 *
 * 用法：
 *   node scripts/rebirth_watch.mjs --scan          # 只读：每线一行（压缩/输入/轮数/是否命中）
 *   node scripts/rebirth_watch.mjs --tick          # 静默接线：平时**零输出**，命中才发信（见下）
 *   node scripts/rebirth_watch.mjs --check <线名>  # 该线现在是否命中（退出码 0=命中）——当"核于戳"的核法用
 *   node scripts/rebirth_watch.mjs --self-test     # 判别性用例：爆表的必须报、正常的必须不报
 *
 * 测试钩子（只给 --self-test 用）：`--sessions <dir> --roster <file> --cache <file>` 覆盖真源路径。
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

// ─────────────────────────────────────────────────────────────────────────────
// 判据：**常量 + 来源**。来源 = `AGENTS.md` §「什么时候该重生」（老板 2026-09-13 09:0x 定，锚定）。
//   原文辅判据：「压缩 ≥ 2 次｜累计输入 > 3–5 亿｜300–500 轮或连续高强度 6–8 小时」——
//   区间值一律**取下沿**（早报只花一行字；漏报会让长窗烂在岗上）。改判据只改这三个常量。
const COMPACT_LIMIT = 2;                 // 压缩 ≥ 2 次
const INPUT_TOKEN_LIMIT = 300_000_000;   // 累计输入 > 3 亿（原文给的是 3–5 亿，取下沿）
const TURN_LIMIT = 300;                  // 轮数 ≥ 300（原文给的是 300–500，取下沿）
// ⚠️ **算不了的那条（明说不硬编）**：主判据「**翻文件找线索的时间超过记住的时间**」——
//   它是**人的主观感受**，rollout 里没有对应字段，任何"代用指标"都是我拍脑袋。
//   所以本脚本**不报**这条，只在输出里标 `n/a`；真要判它，得由**那条线自己**说（或老板说）。
const NON_COMPUTABLE = "主判据「翻文件 vs 记住」（主观感受，rollout 无字段 → 算不了，不硬编）";
// 「连续高强度 6–8 小时」需要"活跃时段"的判定口径（间隔多久算断），本轮不纳入，见报告「已知边界」。

// 提醒节奏：命中后**只提醒一次**；同一线要**再次**提醒，必须满足下面之一（防成新的噪声源）。
const REALERT_AFTER_COMPACTIONS = 1;                 // 压缩次数又涨了（真正的恶化信号）
const REALERT_AFTER_MS = 12 * 60 * 60 * 1000;        // 或距上次提醒 ≥ 12 小时

const SCAN_INTERVAL_MS = 10 * 60 * 1000;             // 接线节拍：小工每拍都调，但**最多 10 分钟算一次**

// ② 那一行发给谁（老板原话「给你一行」= 给总监）。**要改成上板只改这里**。
const ALERT_TO = "codex-总监";
const ALERT_AUTHOR = "codex-总监";                    // 先例：〔自动门禁·codex-总监 授权〕——自动动作按授权线实名
const ALERT_PREFIX = "〔自动·重生体检〕";

// ─────────────────────────────────────────────────────────────────────────────
const arg = (name, def = "") => {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith("--") ? process.argv[i + 1] : def;
};
const has = (n) => process.argv.includes(n);
const hhmm = () => new Date(Date.now() + 8 * 3600e3).toISOString().slice(11, 16);
const nfmt = (n) => (n >= 1e8 ? (n / 1e8).toFixed(2) + "亿" : n >= 1e4 ? (n / 1e4).toFixed(1) + "万" : String(n));

const SESSIONS = arg("--sessions", process.env.REBIRTH_WATCH_SESSIONS || path.join(os.homedir(), ".codex", "sessions"));
const ROSTER = arg("--roster", process.env.REBIRTH_WATCH_ROSTER || path.join(ROOT, "outputs", "dialog", "agents.json"));
const CACHE = arg("--cache", process.env.REBIRTH_WATCH_CACHE || path.join(ROOT, "outputs", "rebirth_watch_cache.json"));
const LOG = path.join(ROOT, "outputs", "rebirth_watch.log");
const DRY = process.env.REBIRTH_WATCH_DRY === "1";   // 自测用：不发信，只打印打算做什么
const FORCE = process.env.REBIRTH_WATCH_FORCE === "1"; // 自测用：忽略 10 分钟节拍闸（否则"第二次零输出"是假通过）

// ── 账本定位：文件名里就带 threadId（`rollout-<ts>-<threadId>.jsonl`），列一次目录即可 ──
function indexSessions() {
  const out = new Map();
  let files = [];
  try { files = fs.readdirSync(SESSIONS, { recursive: true }).map(String); } catch { return out; }
  for (const rel of files) {
    if (!rel.endsWith(".jsonl") || !rel.includes("rollout-")) continue;
    const m = rel.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$/);
    if (m) out.set(m[1], path.join(SESSIONS, rel));
  }
  return out;
}

// ── 增量解析：从 offset 起只读新增部分（43MB 的账本不能每拍全量重扫） ──
function metricsFromChunk(text, acc) {
  for (const line of text.split("\n")) {
    if (!line) continue;
    let o;
    try { o = JSON.parse(line); } catch { continue; }
    if (o.type === "compacted") acc.compactions++;
    else if (o.type === "token_usage_record") {
      const u = (o.payload && o.payload.usage) || {};
      acc.inputTokens += Number(u.input_tokens || 0);
    } else if (o.type === "turn_context") {
      const t = o.payload && o.payload.turn_id;
      if (t && !acc.turnIds.has(t)) { acc.turnIds.add(t); acc.turns++; }
    }
  }
  return acc;
}

function measure(file, prev) {
  const st = fs.statSync(file);
  const blank = () => ({ compactions: 0, inputTokens: 0, turns: 0, turnIds: new Set() });
  if (!prev || prev.size > st.size) {                       // 首次 / 账本被轮转 → 全量
    const acc = blank();
    metricsFromChunk(fs.readFileSync(file, "utf8"), acc);
    return { m: acc, size: st.size };
  }
  if (st.size === prev.size) {                              // 没长 → 直接用缓存
    const acc = blank();
    acc.compactions = prev.compactions || 0;
    acc.inputTokens = prev.inputTokens || 0;
    acc.turns = prev.turns || 0;
    acc.turnIds = new Set(prev.turnIds || []);              // 只用于去重，不参与判定
    return { m: acc, size: st.size };
  }
  const fd = fs.openSync(file, "r");
  try {
    const len = st.size - prev.size;
    const buf = Buffer.alloc(len);
    fs.readSync(fd, buf, 0, len, prev.size);
    const acc = blank();
    acc.compactions = prev.compactions || 0;
    acc.inputTokens = prev.inputTokens || 0;
    acc.turns = prev.turns || 0;
    acc.turnIds = new Set(prev.turnIds || []);
    // 只处理**到最后一个换行为止**：半行留到下次（否则会漏 JSON）
    // ★ 字节账要按**原始 buffer** 算（别用"解码后再编码"的长度——多字节字符跨块时会漂移）
    const cut = buf.lastIndexOf(0x0a);                        // 最后一个换行
    if (cut >= 0) metricsFromChunk(buf.subarray(0, cut + 1).toString("utf8"), acc);
    return { m: acc, size: prev.size + (cut >= 0 ? cut + 1 : 0) };
  } finally { fs.closeSync(fd); }
}

function hitsOf(m) {
  const hits = [];
  if (m.compactions >= COMPACT_LIMIT) hits.push(`压缩 ${m.compactions} 次 ≥ ${COMPACT_LIMIT}`);
  if (m.inputTokens > INPUT_TOKEN_LIMIT) hits.push(`累计输入 ${nfmt(m.inputTokens)} > ${nfmt(INPUT_TOKEN_LIMIT)}`);
  if (m.turns >= TURN_LIMIT) hits.push(`轮数 ${m.turns} ≥ ${TURN_LIMIT}`);
  return hits;
}

/** 扫一遍（可写缓存）。返回每线一行。**只读 rollout/名册**。 */
function scan({ writeCache = false } = {}) {
  const roster = JSON.parse(fs.readFileSync(ROSTER, "utf8"));
  const cache = fs.existsSync(CACHE) ? JSON.parse(fs.readFileSync(CACHE, "utf8")) : {};
  const files = indexSessions();
  const bySlug = (cache.files = cache.files || {});
  const rows = [];

  for (const [name, meta] of Object.entries(roster.agents || {})) {
    const m0 = meta || {};
    if (m0.status === "retired") { rows.push({ name, slug: m0.slug, state: "退役", note: "不体检" }); continue; }
    const tid = m0.threadId;
    if (!tid) { rows.push({ name, slug: m0.slug, state: "算不了", note: "名册里没有 threadId（非 Codex 线/无实例）" }); continue; }
    const file = files.get(tid);
    if (!file) { rows.push({ name, slug: m0.slug, tid, state: "算不了", note: "找不到该实例的 rollout 账本" }); continue; }
    const { m, size } = measure(file, bySlug[m0.slug]);
    bySlug[m0.slug] = { path: file, size, compactions: m.compactions, inputTokens: m.inputTokens,
                        turns: m.turns, turnIds: [...m.turnIds].slice(-5000) };
    rows.push({ name, slug: m0.slug, tid, state: "ok",
                compactions: m.compactions, inputTokens: m.inputTokens, turns: m.turns, hits: hitsOf(m) });
  }
  if (writeCache) fs.writeFileSync(CACHE, JSON.stringify(cache, null, 2), "utf8");
  return { rows, cache };
}

// ── 提醒：① 给那条线投一封信（附重生三步 + 差量页/§三 指引）② 给 ALERT_TO 一行（带核于戳） ──
function mailBody(name, m, hits) {
  return [
    `${ALERT_PREFIX}【体检命中 · ${name}】该考虑重生了（这条不是催活，是提示"该换脑"）`,
    ``,
    `**测出来的判据**（数据取自你自己实例的 rollout 账本，非推断）：${hits.join("；")}。`,
    `现状：压缩 ${m.compactions} 次 / 累计输入 ${nfmt(m.inputTokens)} / ${m.turns} 轮。`,
    ``,
    `**重生三步**（换实例、工号不变）：`,
    `① 结清或明交：走之前把能结的结掉，结不掉的逐条进 §三 移交单（卡号 + 等谁 + 核于戳）；`,
    `② 生成重生包 + 差量页：\`node scripts/crew_rebirth.mjs --plan --me ${name} --hours 3\`（**开工先读差量页**）；`,
    `③ 换绑：\`node scripts/crew_rebirth.mjs --auto --me ${name}\`（新实例要自己说出"差量已核 N 条"且数对得上，才换绑）。`,
    ``,
    `口径见 \`AGENTS.md\` §「什么时候该重生」与 §「重生前：结清或明交」；工具与回退见 \`docs/RUNBOOK_BOSS_COMMANDS.md\`。`,
    `**本提示只报不动**：要不要重生由你与你的上级定，脚本不会替你触发。`,
  ].join("\n");
}

function send(list) {
  const actions = [];
  for (const it of list) {
    if (DRY) { actions.push(`DRY mail→${it.to}: ${it.body.split("\n")[0]}`); continue; }
    const f = path.join(os.tmpdir(), `rebirth_watch_${it.to.replace(/[^\w-]/g, "_")}_${Date.now()}.md`);
    fs.writeFileSync(f, it.body, "utf8");
    try {
      const out = execFileSync(process.execPath, [path.join(ROOT, "tools", "mobile_chat", "say.mjs"),
        "--file", f, "--author", ALERT_AUTHOR, "--card", "-", "--mail", "--wake", "--to", it.to],
        { cwd: ROOT, encoding: "utf8", timeout: 120000 });
      actions.push(String(out).trim());
    } catch (e) {
      actions.push(`发信失败 → ${it.to}：${String((e && (e.stdout || e.message)) || e).slice(0, 200)}`);
    } finally { try { fs.unlinkSync(f); } catch {} }
  }
  return actions;
}

function stamp(slug, name, m) {
  // 「核于」戳：带一条**可复算**的核法（--check 该线）。老板 09:0x 定的纪律。
  const claim = `「${name}」命中重生辅判据（压缩 ${m.compactions} / 输入 ${m.inputTokens} / 轮数 ${m.turns}）`;
  const cmd = `node scripts/rebirth_watch.mjs --check ${name}`;
  try {
    return String(execFileSync(process.execPath, [path.join(ROOT, "scripts", "evidence.mjs"),
      "--claim", claim, "--cmd", cmd], { cwd: ROOT, encoding: "utf8", timeout: 60000 })).trim();
  } catch (e) {
    return `核于 ${hhmm()}｜核法 \`${cmd}\`｜结果 **FAIL**（拿戳失败：${String((e && e.message) || e).slice(0, 120)}）`;
  }
}

function logLine(s) {
  try { fs.appendFileSync(LOG, `[${new Date().toLocaleString("zh-CN")}] ${s}\n`, "utf8"); } catch {}
}

// ── ① --scan ────────────────────────────────────────────────────────────────
function cmdScan() {
  const { rows } = scan({ writeCache: false });
  console.log("线 | 状态 | 压缩次数 | 累计输入 | 轮数 | 命中");
  console.log("--- | --- | --- | --- | --- | ---");
  for (const r of rows) {
    if (r.state !== "ok") { console.log(`${r.name} | ${r.state} | - | - | - | ${r.note}`); continue; }
    console.log(`${r.name} | ok | ${r.compactions} | ${nfmt(r.inputTokens)} | ${r.turns} | ${r.hits.length ? "**命中**：" + r.hits.join("；") : "未命中"}`);
  }
  console.log(`\n阈値（来源 AGENTS.md「什么时候该重生」）：压缩 ≥ ${COMPACT_LIMIT}｜累计输入 > ${nfmt(INPUT_TOKEN_LIMIT)}｜轮数 ≥ ${TURN_LIMIT}`);
  console.log(`算不了：${NON_COMPUTABLE}`);
}

// ── ② --tick（静默接线） ────────────────────────────────────────────────────
function cmdTick() {
  const cache = fs.existsSync(CACHE) ? JSON.parse(fs.readFileSync(CACHE, "utf8")) : {};
  const last = cache.lastTickMs || 0;
  if (!FORCE && Date.now() - last < SCAN_INTERVAL_MS) return 0;   // 静默：没到点直接退
  const { rows, cache: c2 } = scan({ writeCache: false });
  c2.lastTickMs = Date.now();
  const alerted = (c2.alerted = c2.alerted || {});
  const out = [];

  for (const r of rows) {
    if (r.state !== "ok" || !r.hits.length) continue;
    const prev = alerted[r.slug];
    const escalated = prev && r.compactions >= (prev.compactions || 0) + REALERT_AFTER_COMPACTIONS;
    const stale = prev && Date.now() - Date.parse(prev.at) >= REALERT_AFTER_MS;
    if (prev && !escalated && !stale) continue;             // 已报过且没恶化 → **不说话**
    const m = { compactions: r.compactions, inputTokens: r.inputTokens, turns: r.turns };
    out.push({ to: r.name, body: mailBody(r.name, m, r.hits) });
    const line = `${ALERT_PREFIX}【体检命中】${r.name}：${r.hits.join("；")}。只报不动，重生与否由那条线及其上级定。`;
    out.push({ to: ALERT_TO, body: `${line}\n${stamp(r.slug, r.name, m)}` });
    alerted[r.slug] = { at: new Date().toISOString(), ...m };
  }

  fs.writeFileSync(CACHE, JSON.stringify(c2, null, 2), "utf8");
  if (!out.length) return 0;                                // ★ 平时零输出
  const acts = send(out);
  for (const a of acts) { if (DRY) console.log(a); else logLine(a); }
  return 0;
}

// ── ③ --check <线名> ───────────────────────────────────────────────────────
function cmdCheck(name) {
  const { rows } = scan({ writeCache: false });
  const r = rows.find((x) => x.name === name || x.slug === name);
  if (!r) { console.log(`找不到这条线：${name}`); return 2; }
  if (r.state !== "ok") { console.log(`${r.name} → ${r.state}：${r.note}`); return 2; }
  console.log(`${r.name}：压缩 ${r.compactions} / 输入 ${r.inputTokens} / 轮数 ${r.turns} → ${r.hits.length ? "命中：" + r.hits.join("；") : "未命中"}`);
  return r.hits.length ? 0 : 1;
}

/** --assert-quiet：断言"当前没有任何一条命中"（= 接线处于静默态）。退出码 0 = 静默成立。 */
function cmdAssertQuiet() {
  const { rows } = scan({ writeCache: false });
  const measured = rows.filter((r) => r.state === "ok");
  const hot = measured.filter((r) => r.hits.length);
  const unknown = rows.filter((r) => r.state === "算不了");
  console.log(`体检 ${measured.length} 条｜命中 ${hot.length} 条｜算不了 ${unknown.length} 条`);
  if (hot.length) { console.log("命中：" + hot.map((r) => r.name).join("、")); return 1; }
  console.log("静默态成立：当前没有任何一条命中 —— 接线不会说话 ✓");
  return 0;
}

// ── ④ --self-test：判别性用例（爆表必须报、正常必须不报） ─────────────────────
function cmdSelfTest() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "rebirth-watch-"));
  const sess = path.join(tmp, "sessions"); fs.mkdirSync(sess, { recursive: true });
  const T_HOT = "11111111-1111-1111-1111-111111111111";
  const T_CALM = "22222222-2222-2222-2222-222222222222";
  const mk = (tid, { comp, tokens, turns }) => {
    const lines = [JSON.stringify({ type: "session_meta", payload: { session_id: tid, cwd: tmp } })];
    for (let i = 0; i < comp; i++) lines.push(JSON.stringify({ type: "compacted", payload: { message: "x" } }));
    for (let i = 0; i < turns; i++) lines.push(JSON.stringify({ type: "turn_context", payload: { turn_id: `${tid}-t${i}` } }));
    if (tokens) lines.push(JSON.stringify({ type: "token_usage_record", payload: { usage: { input_tokens: tokens } } }));
    fs.writeFileSync(path.join(sess, `rollout-2026-09-13T00-00-00-${tid}.jsonl`), lines.join("\n") + "\n", "utf8");
  };
  mk(T_HOT, { comp: 2, tokens: 400_000_000, turns: 320 });   // 爆表：三条判据全中
  mk(T_CALM, { comp: 0, tokens: 5_000_000, turns: 12 });     // 正常：一条都不中

  const roster = path.join(tmp, "agents.json");
  fs.writeFileSync(roster, JSON.stringify({ agents: {
    "假·爆表线": { slug: "fake-hot", status: "active", threadId: T_HOT },
    "假·正常线": { slug: "fake-calm", status: "active", threadId: T_CALM },
    "假·无实例线": { slug: "fake-none", status: "active" },
    "假·退役线": { slug: "fake-retired", status: "retired", threadId: T_HOT },
  } }), "utf8");

  const cache = path.join(tmp, "cache.json");
  const base = ["--sessions", sess, "--roster", roster, "--cache", cache];
  const run = (args) => {
    const opts = {
      cwd: ROOT,
      encoding: "utf8",
      env: { ...process.env, REBIRTH_WATCH_DRY: "1", REBIRTH_WATCH_FORCE: "1" },
      timeout: 120000,
    };
    try {
      const out = execFileSync(process.execPath, [fileURLToPath(import.meta.url), ...args, ...base], opts);
      return { code: 0, out };
    } catch (e) {
      return { code: e.status || 1, out: String((e.stdout || "") + (e.stderr || "")) };
    }
  };

  let bad = 0;
  const assert = (name, cond, extra = "") => { console.log((cond ? "PASS  " : "FAIL  ") + name + (cond ? "" : "   -> " + extra)); if (!cond) bad++; };

  const s = run(["--scan"]).out;
  assert("爆表线 → 判**命中**（三条判据全中）", /假·爆表线 \| ok \| 2 \| 4\.00亿 \| 320 \| \*\*命中\*\*/.test(s), s.split("\n").find((l) => l.includes("爆表")) || s);
  assert("正常线 → 判**未命中**", /假·正常线 \| ok \| 0 \| 500\.0万 \| 12 \| 未命中/.test(s), s.split("\n").find((l) => l.includes("正常")) || s);
  assert("无实例线 → **算不了**（不硬编、不当命中）", /假·无实例线 \| 算不了/.test(s), s);
  assert("退役线 → 不体检", /假·退役线 \| 退役/.test(s), s);
  assert("扫表里**明说**主判据算不了", s.includes("算不了") && s.includes("翻文件"), s.split("\n").slice(-3).join(" | "));

  assert("--check 爆表线 → 退出码 0（可当核于戳的核法）", run(["--check", "假·爆表线"]).code === 0);
  assert("--check 正常线 → 退出码 1（不命中）", run(["--check", "假·正常线"]).code === 1);

  const dry = run(["--tick"]).out;
  assert("--tick 命中时：**只给爆表线 + 总监**各一封，正常线**一封都没有**",
    dry.includes("DRY mail→假·爆表线") && dry.includes("DRY mail→" + ALERT_TO) && !dry.includes("→假·正常线"), dry);
  const dry2 = run(["--tick"]).out;
  assert("--tick 第二次（未恶化）→ **零输出**（不重复吵）", dry2.trim() === "", dry2);

  // 恶化信号：压缩次数 +1 → 应再次提醒
  fs.appendFileSync(path.join(sess, `rollout-2026-09-13T00-00-00-${T_HOT}.jsonl`),
    JSON.stringify({ type: "compacted", payload: { message: "y" } }) + "\n", "utf8");
  const dry3 = run(["--tick"]).out;
  assert("压缩次数再涨 → **再次提醒**（恶化才说话）", dry3.includes("DRY mail→假·爆表线"), dry3);

  console.log(`\n自测结果：${bad === 0 ? "全部通过" : "失败 " + bad + " 条"}`);
  try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {}
  return bad === 0 ? 0 : 1;
}

// ── 入口 ────────────────────────────────────────────────────────────────────
let rc = 0;
if (has("--self-test")) rc = cmdSelfTest();
else if (has("--scan")) cmdScan();
else if (has("--tick")) rc = cmdTick();
else if (has("--check")) rc = cmdCheck(arg("--check"));
else if (has("--assert-quiet")) rc = cmdAssertQuiet();
else {
  console.log("用法：");
  console.log("  node scripts/rebirth_watch.mjs --scan             # 只读：每线一行（压缩/输入/轮数/命中）");
  console.log("  node scripts/rebirth_watch.mjs --tick            # 静默接线：平时零输出，命中才发信");
  console.log("  node scripts/rebirth_watch.mjs --check <线名>    # 该线现在是否命中（0=命中）");
  console.log("  node scripts/rebirth_watch.mjs --assert-quiet    # 断言「当前零命中」（0=静默态成立）");
  console.log("  node scripts/rebirth_watch.mjs --self-test       # 判别性用例");
  console.log(`\n阈値来源：AGENTS.md「什么时候该重生」｜压缩 ≥ ${COMPACT_LIMIT}｜输入 > ${nfmt(INPUT_TOKEN_LIMIT)}｜轮数 ≥ ${TURN_LIMIT}`);
  console.log(`算不了：${NON_COMPUTABLE}`);
}
process.exit(rc);
