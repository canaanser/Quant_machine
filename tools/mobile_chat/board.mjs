import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import os from "node:os";
import { spawn, execFile } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Codex CLI 可执行文件。**不许再写死版本哈希**（2026-09-11 22:2x 实测：App 更新后目录
// 从 `fd4c151a…` 变成了 `7ac07f4c…`，写死的那份直接消失 → 连"试着注入"都 ENOENT，
// 这是"叫不醒"的第二个独立成因）。解析顺序：
//   ① env `MCHAT_CODEX_BIN`（自测指向桩程序 / 手工指定）
//   ② PATH（现在 PATH 里就有 codex.exe）
//   ③ `%LOCALAPPDATA%\OpenAI\Codex\bin\<版本哈希>\codex.exe` 里**按修改时间取最新**
// 结果缓存 30 秒：App 半夜升级也不用重启 Hub。
const CODEX_BIN_ENV = process.env.MCHAT_CODEX_BIN || "";
let codexBinCache = { at: 0, path: "" };
function resolveCodexBin() {
  if (CODEX_BIN_ENV) return CODEX_BIN_ENV;
  if (codexBinCache.path && Date.now() - codexBinCache.at < 30000) return codexBinCache.path;
  let found = "";
  for (const d of String(process.env.PATH || "").split(";")) {
    if (!d) continue;
    try {
      const p = path.join(d, "codex.exe");
      if (fs.statSync(p).isFile()) { found = p; break; }
    } catch {}
  }
  if (!found) {
    try {
      const binRoot = path.join(process.env.LOCALAPPDATA || "", "OpenAI", "Codex", "bin");
      let best = null;
      for (const name of fs.readdirSync(binRoot)) {
        const p = path.join(binRoot, name, "codex.exe");
        try {
          const st = fs.statSync(p);
          if (st.isFile() && (!best || st.mtimeMs > best.mtimeMs)) best = { p, mtimeMs: st.mtimeMs };
        } catch {}
      }
      if (best) found = best.p;
    } catch {}
  }
  codexBinCache = { at: Date.now(), path: found };
  if (!found) log("CODEX BIN 解析失败：env/PATH/安装目录都没找到 codex.exe");
  return found;
}
// 自测专用：允许把 CODEX 指向 .cmd 桩程序（Windows 下跑 .cmd 需要 shell:true）。
// 生产默认 shell:false（参数不过 shell，避免注入面）。
const CODEX_SHELL = process.env.MCHAT_CODEX_SHELL === "1";
// 工作区路径：**必须可覆盖**（可移植性的第一道门）——搬到别的项目只改 env，不改代码。
const WORKSPACE = process.env.MCHAT_WORKSPACE || "E:\\stockgate\\Quant_Alpha_System";
const HOST = process.env.MCHAT_HOST || "100.64.75.72";
const PORT = Number(process.env.BOARD_PORT || 8788);
const DATA_DIR = process.env.MCHAT_DATA || path.join(os.homedir(), ".codex", "mobile_chat");
const TURN_TIMEOUT_MS = Number(process.env.MCHAT_TIMEOUT_MS || 240000);

const BOARD_FILE = process.env.MCHAT_BOARD_FILE || path.join(WORKSPACE, "docs", "COMMS_BOARD.md");
const INBOX_DIR = process.env.MCHAT_INBOX_DIR || path.join(WORKSPACE, "outputs", "inbox");
const HEART_FILE = path.join(WORKSPACE, "outputs", "watch_heartbeat.txt");
const WATCH_EVENTS = [
  "09:20", "10:00", "10:30", "11:15", "11:30",
  "13:10", "14:00", "14:30", "14:44", "15:08",
];
const TOKEN_FILE = path.join(DATA_DIR, "token.txt");
// 泛称黑名单：署名与**入职名字**都不许用。泛称 = "写的人没说自己是谁"，
// 接受它等于把"看板上分不清谁在说"这个老问题合法化（老板 2026-09-11 定）。
// /api/post 与 /api/onboard 共用这一份，免得两处名单漂移。
const GENERIC_BOARD_NAMES = ["codex", "dsh", "ds h", "deepseek", "助手", "agent", "ai"];
const STATE_FILE = path.join(DATA_DIR, "state.json");
const LAST_FILE = path.join(DATA_DIR, "last_board.txt");
const LOG_FILE = path.join(DATA_DIR, "log.txt");
const DIALOG_FILE = process.env.MCHAT_DIALOG_FILE || path.join(WORKSPACE, "outputs", "dialog", "dialog.ndjson");
// 历史归档：热文件超过阈值就把"老的"挪去 dialog.archived.ndjson（只重新挂载、不物理删）。
// 目的：长期把 /api/dialog 的解析成本钉在常数级，而不是随年月线性变慢。
const DIALOG_ARCHIVE_FILE = process.env.MCHAT_DIALOG_ARCHIVE || DIALOG_FILE + ".archived";
const DIALOG_MAX_BYTES = Number(process.env.MCHAT_DIALOG_MAX_BYTES || 4 * 1024 * 1024);
const DIALOG_KEEP_LINES = Number(process.env.MCHAT_DIALOG_KEEP_LINES || 2000);
const PROGRESS_FILE = path.join(WORKSPACE, "outputs", "dialog", "dsh_progress.ndjson");
const AGENTS_FILE =
  process.env.MCHAT_AGENTS_FILE || path.join(WORKSPACE, "outputs", "dialog", "agents.json");
// 各线的“看板信箱”目录（本尊不在/在忙时把留言落盘的地方）。
// 单独给 env：自测要把它指到临时目录，否则会写进真实 outputs/dialog（旧毛病）。
const MAILBOX_DIR = process.env.MCHAT_MAILBOX_DIR || path.join(WORKSPACE, "outputs", "dialog");
// 运行态/工程文件目录（名册、群组、暂停闸、任务态、已读游标、物料、待老板事件…）。
// 与"信箱"分开的理由：**生命周期不同**——信箱是队列（会被消费、会搬走），
// 这些是可重建/需长期留的状态。默认仍是老位置（行为不变），迁移时用 env 指到新目录。
const STATE_DIR = process.env.MCHAT_STATE_DIR || MAILBOX_DIR;
// 任务改号别名表：**数据文件**，不是硬编码。真源 tools/mobile_chat/task_id_aliases.json
// （口径见 docs/TASK_ID_STANDARD.md §四）。以后再改号只改那个 json——不用改代码、不用重启（5 秒热加载）。
const TASK_ID_ALIAS_FILE =
  process.env.MCHAT_TASK_ID_ALIASES || path.join(__dirname, "task_id_aliases.json");
// 闲置会话停用清单（老板 2026-09-12 00:0x A 方案）：仓库版 + state 版取并集。
// 停用=只标记不删历史；作用是**别把睡着的 AI 会话叫起来**（老代码会把没会话的投递回落到它）。
const RETIRED_THREADS_FILE =
  process.env.MCHAT_RETIRED_THREADS || path.join(__dirname, "retired_threads.json");
let retiredCache = { at: 0, map: {} };
function retiredThreadIds() {
  if (Date.now() - retiredCache.at < 30000 && retiredCache.at) {
    return { ...retiredCache.map, ...((readState().retiredThreads) || {}) };
  }
  let map = {};
  try {
    const obj = JSON.parse(fs.readFileSync(RETIRED_THREADS_FILE, "utf8"));
    map = obj.retired || {};
  } catch (e) {
    if (!retiredCache.at) log("RETIRED THREADS FILE UNREADABLE (忽略):", e.message);
  }
  retiredCache = { at: Date.now(), map };
  return { ...map, ...((readState().retiredThreads) || {}) };
}
// 页面"体检上报"落点：手机/浏览器把自己看到的渲染结果报回来，服务端落盘，
// 这样在"我看不到屏幕"的情况下也能读到它的真实状态（记录数/渲染行数/消息区高度/报错）。
const UI_REPORT_FILE = process.env.MCHAT_UI_REPORT || path.join(WORKSPACE, "outputs", "dialog", "ui_report.json");
const DIALOG_CTX_N = Number(process.env.MCHAT_DIALOG_CTX || 25);
// 页面版本：改动页面时把它 +1。服务把它塞进 /api/ping，页面发现对不上就自动整页刷新，
// 这样手机端不会一直跑着旧的 JS（今天已经因为旧页面误诊过两次）。
const PAGE_VER = "2026-09-10.50"; // .50：HUB-004 派单页（手机端表单 + 三态结果）
// ————————————————————————————————————————————————
// 看板命名真源：docs/BOARD_NAMES.md（老板 2026-09-10 定）。
// 规则：每个实例只有一串名字 `前缀-短名`（dsh- / codex-），`老板` 例外；
// 这串名字同时用于 ①对话框标题 ②状态栏（agents.json 的 label）③看板 @ 句柄
// ④看板行尾署名 ⑤inbox 指派名（instance/claimedBy）。
// 旧句柄（@dsh/@dsh-main/@codex/@codex-convtool）全部保留兼容，只是解析成同一串新名。
const BOARD_NAMES = {
  "老板": "老板",
  boss: "老板",
  // 公告：发给所有线，只看不回（老板 2026-09-11 01:5x）
  "全体": "全体",
  all: "全体",
  // dsh 侧
  dsh: "dsh-老员工",
  "dsh-main": "dsh-老员工",
  "dsh-老员工": "dsh-老员工",
  "dsh-quant": "dsh-quant",
  // codex 侧
  codex: "codex-看板服务",
  "codex-看板服务": "codex-看板服务",
  "codex-convtool": "codex-看板编辑",
  "codex-看板编辑": "codex-看板编辑",
  "codex-看板助理": "codex-看板助理",
  "codex-dsh唤醒": "codex-唤醒通道",
  "codex-唤醒通道": "codex-唤醒通道",
  "codex-量化总监": "codex-量化总监",
  "codex-总监": "codex-总监",
};
const CODEX_SERVICE = "codex-看板服务"; // 看板服务自己那条常驻会话（旧泛称 Codex / 旧句柄 @codex 的真实落点）
const DSH_PRIMARY = "dsh-老员工";
const DSH_HEADLESS = "dsh-quant"; // 桥的 headless 执行线（进度流就是它跑的）
function boardName(raw) {
  const key = String(raw == null ? "" : raw).trim().replace(/^@/, "");
  if (!key) return "";
  return BOARD_NAMES[key.toLowerCase()] || key;
}

// —— 全渠道归一（第一期）——
const INBOX_DONE_DIR = path.join(INBOX_DIR, "done");
const BRIDGE_DIR =
  process.env.MCHAT_BRIDGE_DIR ||
  "\\\\wsl.localhost\\Ubuntu-24.04\\home\\lgy\\.dsh-codex-bridge";
const CLAIM_TIMEOUT_MS = Number(process.env.MCHAT_CLAIM_TIMEOUT_MS || 15 * 60 * 1000);
const BRIDGE_BODY_MAX = Number(process.env.MCHAT_BRIDGE_BODY_MAX || 1500);
// 绑定派发（codex exec resume <会话>）会在那条会话里真跑一个回合，期间桌面端拿不到写锁
// （唤醒通道 2026-09-10 23:33 报的缺陷：老板 @量化总监 时输入框被锁）。
const THREAD_LOCKS = process.env.MCHAT_THREAD_LOCKS || "C:\\Users\\Administrator\\.codex\\thread-writer-locks";
const BOUND_TIMEOUT_MS = Number(process.env.MCHAT_BOUND_TIMEOUT_MS || 120000);
// 值守分线：本尊（桌面端那条对话）不在时，由服务自己持有的一条专属会话**以本线名义**回话。
// 老板 2026-09-11 01:3x 的想法："不管你现在忙不忙，它都帮你把信箱里的东西以你的形式回复给我。"
const DUTY = {
  alias: "codex-看板编辑",
  slug: "codex-convtool",
  pollMs: Number(process.env.MCHAT_DUTY_POLL_MS || 20000),
  maxPerHour: Number(process.env.MCHAT_DUTY_MAX_PER_HOUR || 10),
  maxAgeMs: Number(process.env.MCHAT_DUTY_MAX_AGE_MS || 3 * 3600 * 1000),
  timeoutMs: Number(process.env.MCHAT_DUTY_TIMEOUT_MS || 180000),
};
// 代答标签：老板 2026-09-11 08:1x 定 —— "你就标注一个代答标签就行了，前面不用加那么多解释"。
// 所以所有代答一律只加这一枚标签，正文直接是人话，不再写"本尊这会儿不在，由…代答"那种长句。
const DUTY_TAG = "〔代答〕";
// 承诺类字样：命中就给这行再挂一枚小标签（老板 2026-09-11 22:5x："以最小化，就是前面加个圆角框，
// 跟代答那个模式一样"）。**不写长句**——标签本身就是声明。
const DUTY_PROMISE_TAG = "〔承诺需本尊确认〕";
const DUTY_PROMISE_RE = /同意|批准|认可|认领|签字|签署|承诺|答应|授权|拍板|同意书|批准书/;
// "在吗"这类**在场询问**：只回一个字（老板 2026-09-11 23:38 反馈：拿一段无关旧话去引述很蠢）
const DUTY_PRESENCE_RE = /^(在吗|在不在|在么|你在吗|还在吗|在吗？|在吗\?|在\?|在？)[\s～!！。]*$/;

// （已删除 2026-09-12 00:0x：`PERSONA` / `parseThreadId()` —— 那是"没会话就新建一条看板服务会话"的
//  老路子留下的。老板 A 方案停用了那三条闲置会话，投递现在必须显式指定目标会话，这两段成了死代码。）
let busy = false;
let shuttingDown = false;
let boardTimer = null;
let watcherReady = false;

function log(...parts) {
  const line = `${new Date().toISOString()}  ${parts.join(" ")}\n`;
  try {
    fs.appendFileSync(LOG_FILE, line);
  } catch {}
  process.stdout.write(line);
}

function ensureDataDir() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

function ensureBoardFile() {
  fs.mkdirSync(path.dirname(BOARD_FILE), { recursive: true });
  if (!fs.existsSync(BOARD_FILE)) {
    fs.writeFileSync(
      BOARD_FILE,
      [
        "# 共享看板（老板 / dsh-老员工 / codex-*）",
        "",
        "日常沟通阵地：直接往下追加，不要改历史条目。",
        "每行格式：`- @谁 时间 作者：内容`",
        "命名规约：每个实例只用一串名字 `前缀-短名`，@句柄 = 行尾署名（真源 docs/BOARD_NAMES.md）。",
        "- @dsh-老员工 由 dsh 值守主会话回复；@codex-看板服务 由看板常驻会话回复；@老板 的消息留给老板看。",
        "- 旧句柄 @dsh / @dsh-main / @codex / @codex-convtool 仍可用，只是不再新写进署名。",
        "给某条线投信（本尊不在时由它的值守分线回话）：往 outputs/dialog/pending_<slug>.ndjson 追加一行，",
        "或 POST /api/mail {to,from,body}。详见 docs/BOARD_MAILBOX.md（公共接口，所有线含新建账号通用）。",
        "",
      ].join("\n")
    );
  }
}

function readToken() {
  ensureDataDir();
  try {
    const t = fs.readFileSync(TOKEN_FILE, "utf8").trim();
    if (t.length >= 16) return t;
  } catch {}
  const token = crypto.randomBytes(24).toString("hex");
  fs.writeFileSync(TOKEN_FILE, token, { mode: 0o600 });
  return token;
}

function readState() {
  try {
    return JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
  } catch {
    return {};
  }
}

function writeState(state) {
  ensureDataDir();
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
}

function tokensEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string") return false;
  const ba = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ba.length !== bb.length) return false;
  return crypto.timingSafeEqual(ba, bb);
}

function runCodex(args, input, timeoutMs) {
  return new Promise((resolve, reject) => {
    const bin = resolveCodexBin();
    if (!bin) {
      reject(new Error("找不到 codex.exe（env/PATH/安装目录都试过了）"));
      return;
    }
    const child = spawn(bin, args, {
      cwd: WORKSPACE,
      windowsHide: true,
      shell: CODEX_SHELL,
    });
    let stdout = "";
    let stderr = "";
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      try {
        child.kill();
      } catch {}
      try {
        execFile("taskkill", ["/PID", String(child.pid), "/T", "/F"], () => {});
      } catch {}
      const lim = timeoutMs || TURN_TIMEOUT_MS;
      reject(new Error("等待 Codex 回复超时（超过 " + Math.round(lim / 60000) + " 分钟）"));
    }, timeoutMs || TURN_TIMEOUT_MS);

    child.stdout.on("data", (d) => {
      stdout += d.toString("utf8");
    });
    child.stderr.on("data", (d) => {
      stderr += d.toString("utf8");
    });
    child.on("error", (err) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(err);
    });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ code, stdout, stderr });
    });

    child.stdin.on("error", () => {});
    child.stdin.write(input, "utf8");
    child.stdin.end();
  });
}

// ══════════════════════════════════════════════════════════════
// REQ-HUB-004b 投递即唤醒（总监 2026-09-11 22:14 派，老板 22:4x 点头）
//   首选 `codex queue --thread <tid> --message <文本>`：**穿透写锁**（总监 21:42 实测：
//   对已打开、被持锁的线投递成功，该线当场起回合）；
//   备选 `codex exec resume`（窗口关着时它反而能成）；
//   都不行 → 落它信箱 + 看板标「已投递未唤醒」。**绝不代答、绝不谎报。**
//   护栏：实名署名、每线 10 分钟冷却、每小时上限、幂等（同一条不重复投）、每次投递写日志。
// ══════════════════════════════════════════════════════════════
// 冷却的真实目的：**防轰炸**，不是**防聊天**（老板 2026-09-12 01:0x 发现两条消息被"阻塞"）。
// 所以：① 硬冷却只留 90 秒（手快连发也不会被挡太久）；② **同一条消息**十分钟内不重复投（幂等）；
//       ③ 真正的闸门是**每小时上限**（默认 20），别拿冷却当闸门。
const QUEUE_COOLDOWN_MS = Number(process.env.MCHAT_QUEUE_COOLDOWN_MS || 90 * 1000);
const QUEUE_MAX_PER_HOUR = Number(process.env.MCHAT_QUEUE_MAX_PER_HOUR || 20);
const QUEUE_DUP_MS = Number(process.env.MCHAT_QUEUE_DUP_MS || 10 * 60 * 1000);
function queueTextHash(text) {
  // 去重键按**内容**算，不按"包装后的整段"：包装里带时间（"（看板留言，来自 X，时间 01:2x）"），
  // 同一句话跨一分钟就变成两个哈希，会重复投递（自测里真实抓到过）。所以先剥掉最外层的包装。
  const s = String(text || "").replace(/^（[^）]*）\s*/, "").trim();
  return crypto.createHash("sha1").update(s || String(text || "")).digest("hex").slice(0, 12);
}
function queueLastText(alias) {
  const map = readState().queueText || {};
  return map[alias] || null;
}
function markQueueText(alias, hash) {
  const st = readState();
  const map = { ...(st.queueText || {}) };
  map[alias] = { hash: hash, at: Date.now() };
  writeState({ ...st, queueText: map });
}
function queueHourCount(alias) {
  const hist = (readState().queueSent || {})[alias];
  return (Array.isArray(hist) ? hist : []).filter((t) => Date.now() - Number(t) < 3600 * 1000).length;
}
function queueCooldownLeft(alias) {
  const hist = (readState().queueSent || {})[alias];
  if (!Array.isArray(hist) || !hist.length) return 0;
  return Math.max(0, QUEUE_COOLDOWN_MS - (Date.now() - Number(hist[hist.length - 1])));
}
function markQueueSent(alias) {
  const st = readState();
  const all = { ...(st.queueSent || {}) };
  const hist = (Array.isArray(all[alias]) ? all[alias] : []).filter((t) => Date.now() - Number(t) < 3600 * 1000);
  hist.push(Date.now());
  all[alias] = hist.slice(-50);
  writeState({ ...st, queueSent: all });
}
// 投递 = 把留言"塞进那条会话的队列"，它会被 app-server 叫起来自己处理（我们**不替它说**）
async function deliverByQueue(alias, text) {
  const meta = agentFor(alias) || {};
  const tid = meta.threadId ? String(meta.threadId) : "";
  if (!tid) return { ok: false, how: "no-thread" };
  // 停用会话清单（老板 A 方案）：退休的会话不再投递，免得把睡着的 AI 唤醒
  if (retiredThreadIds()[tid]) {
    log("RETIRED THREAD: 不投递", alias, tid.slice(0, 8));
    return { ok: false, how: "retired-thread" };
  }
  // 同一条消息十分钟内不重复投（幂等；重复扫描/重试都不会再叫一次）
  const hash = queueTextHash(text);
  const lastT = queueLastText(alias);
  if (lastT && lastT.hash === hash && Date.now() - Number(lastT.at || 0) < QUEUE_DUP_MS) {
    return { ok: true, how: "dup-skip" };
  }
  const cd = queueCooldownLeft(alias);
  if (cd > 0) return { ok: false, how: "cooldown", leftSec: Math.round(cd / 1000) };
  if (queueHourCount(alias) >= QUEUE_MAX_PER_HOUR) return { ok: false, how: "hourly-limit" };
  const t0 = Date.now();
  try {
    const out = await runCodex(["queue", "--thread", tid, "--message", text], "", 30000);
    if (out.code !== 0) {
      return { ok: false, how: "queue-failed", ms: Date.now() - t0, error: String(out.stderr || "").slice(-200) };
    }
    markQueueSent(alias);
    markQueueText(alias, hash);
    return { ok: true, how: "queue", ms: Date.now() - t0 };
  } catch (e) {
    return { ok: false, how: "queue-error", ms: Date.now() - t0, error: String(e.message).slice(0, 200) };
  }
}
// 统一投递口：queue（首选）→ resume（备选）。返回值只描述事实，不含任何"替它说的话"。
async function deliverToLine(alias, text) {
  const q = await deliverByQueue(alias, text);
  if (q.ok) {
    log("DELIVERED+WOKEN:", alias, "via=queue", (q.ms || 0) + "ms");
    return { ok: true, how: "queue" };
  }
  const tid = agentFor(alias).threadId ? String(agentFor(alias).threadId) : "";
  if (!tid) return { ok: false, how: "no-thread", queue: q }; // 没有会话就别去唤那条闲置的
  if (q.how !== "no-thread") {
    log("QUEUE MISS:", alias, q.how, q.error ? String(q.error).slice(0, 80) : "");
  }
  try {
    const reply = await chatOnce(text, tid, BOUND_TIMEOUT_MS);
    log("DELIVERED+WOKEN:", alias, "via=resume");
    return { ok: true, how: "resume", reply: reply };
  } catch (e) {
    return { ok: false, how: q.how === "no-thread" ? "no-thread" : "failed", queue: q, error: String(e.message).slice(0, 200) };
  }
}

function readLastMessage() {
  try {
    const t = fs.readFileSync(LAST_FILE, "utf8").trim();
    if (t) return t;
  } catch {}
  return "";
}

async function chatOnce(message, threadIdOverride, timeoutMs) {
  const state = readState();
  // ⚠ 2026-09-12 00:0x 老板 A 方案：**不再回落到 `boardThreadId`**。
  //   老实现给了"没会话就去用/新建看板服务那条闲置会话"的口子——等于睡着的 AI 会被误唤醒。
  //   现在投递必须**显式指定目标会话**（目标线的 threadId）；没有就由调用方走"落信箱"。
  const threadId = threadIdOverride ? String(threadIdOverride) : "";
  if (!threadId) throw new Error("没有指定会话（投递必须有目标 threadId）");
  let out;

  out = await runCodex(
    ["exec", "resume", "--json", "--skip-git-repo-check", "-o", LAST_FILE, String(threadId), "-"],
    message,
    timeoutMs
  );

  if (out.code !== 0) {
    const tail = (out.stderr || "").trim().slice(-1200);
    throw new Error("Codex 调用失败（退出码 " + out.code + "）：" + (tail || "无错误信息"));
  }

  const reply = readLastMessage();
  if (!reply) throw new Error("Codex 没有返回文字回复");
  return reply;
}

function fmtNow() {
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date());
  const get = (t) => (parts.find((x) => x.type === t) || {}).value || "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}`;
}

function appendBoardLine(target, author, content, extraRefs) {
  ensureBoardFile();
  const text = fs.readFileSync(BOARD_FILE, "utf8");
  const sep = text.endsWith("\n") ? "" : "\n";
  const flat = String(content || "").replace(/\s*\n\s*/g, " ").trim();
  const line = `- @${target} ${fmtNow()} ${author}：${flat}`;
  fs.appendFileSync(BOARD_FILE, sep + line + "\n", "utf8");
  const rec = dialogRecordFromBoardLine(line);
  if (rec && extraRefs) rec.refs = { ...rec.refs, ...extraRefs };
  if (rec) appendDialog(rec);
  log("BOARD APPEND", target, author, String(content || "").slice(0, 60));
  return line;
}

// 看板行解析（唯一入口）。两种写法都认：
//   标准：`- @名字 2026-09-10 21:31 署名：内容`
//   缺日期：`- @名字 21:31 署名：内容`（dsh 侧漏写日期时自动补今天，否则整条会被丢掉）
function entryFromBoardLine(line) {
  const s = String(line || "").trim();
  let m = s.match(/^- @([^\s]+) (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (.+)$/);
  let time = null;
  let rest = null;
  let target = null;
  if (m) {
    target = m[1];
    time = m[2];
    rest = m[3];
  } else {
    const m2 = s.match(/^- @([^\s]+) (\d{1,2}:\d{2}) (.+)$/);
    if (!m2) return null;
    const today = fmtNow().slice(0, 10);
    target = m2[1];
    time = today + " " + String(m2[2]).padStart(5, "0");
    rest = m2[3];
  }
  const ci = rest.search(/[：:]/);
  if (ci < 0) return null;
  const author = rest.slice(0, ci).trim();
  const content = rest.slice(ci + 1).trim();
  if (!author || !content) return null;
  return { target: target.toLowerCase(), time, author, content, line: s };
}

// （已删除 2026-09-12 00:3x：`parseEntries()` —— 与 `entryFromBoardLine()` 重复，零调用点）
const dialogIds = new Set();

// 「已经路由过的看板行」单独记账：入库去重（dialogIds）不能当路由去重——
// 服务自己写行时会顺手入库，若拿入库去重当路由去重，自己写的行就永远不路由了（会漏派单）。
// 用 id 记账而不是字节偏移，是为了不受“别人在文件中间插行”影响。
const routedIds = new Set();
function loadRoutedIds() {
  const st = readState();
  const arr = Array.isArray(st.routedIds) ? st.routedIds : [];
  for (const id of arr) routedIds.add(id);
  // 首次升级：把 Hub 里已有的看板行全部视为“已路由”，否则重启会把历史 @dsh 留言再派一遍。
  if (!arr.length && !st.routedSeeded) {
    for (const r of readDialog(5000)) if (r.refs && r.refs.board && r.id) routedIds.add(r.id);
    saveRoutedIds(true);
    log("ROUTED SEEDED from hub: " + routedIds.size);
  }
}
function saveRoutedIds(force) {
  if (!force && !routedIds.size) return;
  const arr = [...routedIds].slice(-1500);
  writeState({ ...readState(), routedIds: arr, routedSeeded: true });
}

// 忙/超时不再代答：撤回 routed 记账，下一轮重试；超过上限才发一条服务署名状态行。
// （已删除 2026-09-12 00:3x：`requeueCodexEntries()` + `relayRetries` + `RELAY_MAX_RETRY` —— 重派逻辑
//  已被 `routedIds` + HUB-002 的投递判定取代，三个符号零调用点）
function dialogIdFor(text) {
  return crypto.createHash("sha1").update(text).digest("hex").slice(0, 16);
}

// 把任意时间点转成记录用的 +08:00 时刻（与 dialog.v1 的 ts 同格式）
function toCst(date) {
  const src = date instanceof Date && !Number.isNaN(date.getTime()) ? date : new Date();
  const d = new Date(src.getTime() + 8 * 3600 * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return (
    d.getUTCFullYear() + "-" + p(d.getUTCMonth() + 1) + "-" + p(d.getUTCDate()) +
    "T" + p(d.getUTCHours()) + ":" + p(d.getUTCMinutes()) + ":" + p(d.getUTCSeconds()) + "+08:00"
  );
}

function dialogTs() {
  return toCst(new Date());
}

function parseCst(ts) {
  const t = Date.parse(String(ts || ""));
  return Number.isNaN(t) ? 0 : t;
}

function clip(text, max) {
  const s = String(text == null ? "" : text).replace(/\r\n/g, "\n").trim();
  if (s.length <= max) return s;
  return s.slice(0, max) + "\n…（全文 " + s.length + " 字，已截断）";
}

// 桥信箱里可能夹带 dsh web 的启动 URL 之类凭据：入 Hub 前先把 token/密钥位打码。
// Hub 记录会被页面渲染、也会进 dsh 的上下文切片，凭据一律不许落地。
function redact(text) {
  return String(text == null ? "" : text)
    .replace(/([?&]token=)[A-Za-z0-9._-]{8,}/gi, "$1***")
    .replace(/\bsk-[A-Za-z0-9_-]{16,}/g, "sk-***");
}

function ensureDialogFile() {
  fs.mkdirSync(path.dirname(DIALOG_FILE), { recursive: true });
  if (!fs.existsSync(DIALOG_FILE)) fs.writeFileSync(DIALOG_FILE, "");
}

function appendDialog(rec) {
  if (!rec || !rec.id) return false;
  ensureDialogFile();
  if (dialogIds.has(rec.id)) return false;
  fs.appendFileSync(DIALOG_FILE, JSON.stringify(rec) + "\n", "utf8");
  dialogIds.add(rec.id);
  sseNotify("record"); // HUB-007：有新记录 → 推一条无载荷的"变了"，页面秒级刷新
  return true;
}

// ── 性能：**一次解析，多处复用** ──
// 老实现每次 readDialog() 都重读整个文件并 JSON.parse 全部行；而一次 /api/dialog 会调用它
// 5～15 次（每条记录的判定、代答检索、投递判定各来一遍）。这里按 (mtime,size) 缓存解析结果：
// 文件没变就直接复用数组，只有真正写入后才重新解析。**语义完全不变**（仍返回最后 limit 条）。
let dialogCache = { key: "", all: [] };
// 归档进内存：轮转**对读端透明**——读到的仍是"归档 + 热"的完整历史（内存只留最近 ARCHIVE_IN_MEM 条）
const DIALOG_ARCHIVE_IN_MEM = Number(process.env.MCHAT_DIALOG_ARCHIVE_IN_MEM || 20000);
let dialogArchived = [];
function loadDialogArchive() {
  try {
    const lines = fs.readFileSync(DIALOG_ARCHIVE_FILE, "utf8").split("\n").filter(Boolean);
    const keep = lines.slice(-DIALOG_ARCHIVE_IN_MEM);
    const out = [];
    for (const l of keep) {
      try {
        out.push(JSON.parse(l));
      } catch {}
    }
    dialogArchived = out;
  } catch {
    dialogArchived = [];
  }
  return dialogArchived.length;
}
function dialogKey() {
  try {
    const st = fs.statSync(DIALOG_FILE);
    return st.mtimeMs + "/" + st.size;
  } catch {
    return "";
  }
}
function readDialogAll() {
  ensureDialogFile();
  const key = dialogKey();
  if (key && key === dialogCache.key && dialogCache.all.length) {
    return dialogArchived.length ? dialogArchived.concat(dialogCache.all) : dialogCache.all;
  }
  try {
    const lines = fs.readFileSync(DIALOG_FILE, "utf8").split("\n").filter(Boolean);
    const all = [];
    for (const l of lines) {
      try {
        all.push(JSON.parse(l));
      } catch {}
    }
    dialogCache = { key: key, all: all };
    return dialogArchived.length ? dialogArchived.concat(all) : all;
  } catch {
    return dialogArchived.slice();
  }
}
function readDialog(limit = 200) {
  const all = readDialogAll();
  return limit > 0 ? all.slice(-limit) : all;
}

function loadDialogIds() {
  ensureDialogFile();
  // 热文件 + 归档都要装 id：否则轮转后老看板行会被当成"新行"重新入库（重复）
  for (const f of [DIALOG_ARCHIVE_FILE, DIALOG_FILE]) {
    try {
      for (const l of fs.readFileSync(f, "utf8").split("\n")) {
        if (!l.trim()) continue;
        try {
          const r = JSON.parse(l);
          if (r && r.id) dialogIds.add(r.id);
        } catch {}
      }
    } catch {}
  }
}

function dialogRecordFromBoardLine(line) {
  const e = entryFromBoardLine(line);
  if (!e) return null;
  const author = e.author;
  const body = e.content;
  return {
    id: dialogIdFor(e.line),
    ts: e.time.replace(" ", "T") + ":00+08:00",
    // 归一署名与句柄到看板名：历史行里的 DSH / DSH-main / Codex / codex-convtool
    // 在 Hub 里一律呈现成同一串名字（看板文件原文不改写）。
    from: boardName(author),
    to: boardName(e.target),
    channel: "board",
    // 面向"全体"的行 = 公告：所有人可见、谁都不回（不入派单、不唤醒、不代答）
    kind: boardName(e.target) === "全体" ? "notice" : "message",
    body,
    threadId: null,
    // slug：同一岗位跨代（承接/换人）时，能分清"这句话是哪一代说的"。
    // 只对**新入库**的行补；历史行一个字不改写（append-only）。
    refs: { board: true, rawFrom: author, rawTo: e.target, slug: slugFor(boardName(author)) },
    state: "done",
  };
}

function ingestBoardText(text) {
  let n = 0;
  for (const line of String(text || "").split("\n")) {
    const rec = dialogRecordFromBoardLine(line.trim());
    if (rec && appendDialog(rec)) n++;
  }
  return n;
}

// 看板文件归一：**整文件扫描 + 按行内容去重**，不用字节偏移。
// （2026-09-10 教训：几个人同时改看板文件时，行被插到前面/原地改写会让偏移错位，
//  偏移之后的新行就被永久跳过——当天真丢过一条回报。整文件重扫成本可忽略，重复由 id 去重兜住。）
// 看板入库缓存：一次 /api/dialog 会 catchUpDialog() 两遍，而每遍都要把 240KB 看板整读 + 逐行正则。
// 按 (mtime,size) 记住"这份文件已经入过库了"——文件没变就直接 0，真正 append 后才重扫。
let ingestCache = { board: "", progress: "", inbox: "", bridge: "" };
function statKey(p) {
  try {
    const st = fs.statSync(p);
    return st.mtimeMs + "/" + st.size;
  } catch {
    return "";
  }
}
function ingestBoardFile() {
  const key = statKey(BOARD_FILE);
  if (key && key === ingestCache.board) return 0;
  try {
    const full = fs.readFileSync(BOARD_FILE, "utf8");
    const n = ingestBoardText(full);
    ingestCache.board = statKey(BOARD_FILE);
    return n;
  } catch {
    return 0;
  }
}

function catchUpDialog() {
  ingestBoardFile();
  ingestProgress();
  ingestInboxTasks();
  ingestBridgeMail();
  rotateDialogIfNeeded();
}

// 轮转：只在大文件时动手；老行进 archive（**保留 id**，避免重入库），热文件只留最近 N 条。
function rotateDialogIfNeeded() {
  try {
    const st = fs.statSync(DIALOG_FILE);
    if (st.size < DIALOG_MAX_BYTES) return 0;
    const lines = fs.readFileSync(DIALOG_FILE, "utf8").split("\n").filter(Boolean);
    if (lines.length <= DIALOG_KEEP_LINES) return 0;
    const old = lines.slice(0, lines.length - DIALOG_KEEP_LINES);
    const keep = lines.slice(-DIALOG_KEEP_LINES);
    fs.appendFileSync(DIALOG_ARCHIVE_FILE, old.join("\n") + "\n", "utf8");
    fs.writeFileSync(DIALOG_FILE, keep.join("\n") + "\n", "utf8");
    // 同步进内存（读端透明），也顺手让解析缓存失效
    for (const l of old) {
      try {
        dialogArchived.push(JSON.parse(l));
      } catch {}
    }
    if (dialogArchived.length > DIALOG_ARCHIVE_IN_MEM) {
      dialogArchived = dialogArchived.slice(-DIALOG_ARCHIVE_IN_MEM);
    }
    dialogCache = { key: "", all: [] };
    log("DIALOG ROTATED: archived=" + old.length + " keep=" + keep.length);
    return old.length;
  } catch {
    return 0;
  }
}

function ingestProgress() {
  const keyP = statKey(PROGRESS_FILE);
  if (keyP && keyP === ingestCache.progress) return 0;
  try {
    if (!fs.existsSync(PROGRESS_FILE)) return 0;
    const full = fs.readFileSync(PROGRESS_FILE, "utf8");
    const st = readState();
    let off = Number(st.progressOffset || 0);
    if (off > full.length) off = 0;
    if (full.length <= off) return 0;
    const nl = full.lastIndexOf("\n");
    if (nl < off) return 0;
    let n = 0;
    for (const line of full.slice(off, nl + 1).split("\n")) {
      if (!line.trim()) continue;
      let p;
      try {
        p = JSON.parse(line);
      } catch {
        continue;
      }
      const body = String(p.body || "").trim();
      if (!body) continue;
      const rec = {
        id: dialogIdFor("progress|" + (p.taskId || "") + "|" + (p.ts || "") + "|" + body),
        ts: p.ts || dialogTs(),
        from: DSH_HEADLESS,
        to: "none",
        channel: "bridge",
        kind: "progress",
        body,
        threadId: null,
        refs: { taskId: p.taskId || null },
        state: "done",
      };
      if (appendDialog(rec)) n++;
    }
    writeState({ ...readState(), progressOffset: nl + 1 });
    ingestCache.progress = statKey(PROGRESS_FILE);
    return n;
  } catch {
    return 0;
  }
}

// ————————————————————————————————————————————————
// 适配器（进）：inbox 任务 → 标准记录
// 文件本身是唯一真源；记录只写一次（按文件名去重），
// open/done/待办 在读取时按“文件在哪 + 有没有回帖”现算，保证 append-only。
// ————————————————————————————————————————————————
function scanInbox() {
  const out = [];
  for (const [dir, done] of [
    [INBOX_DIR, false],
    [INBOX_DONE_DIR, true],
  ]) {
    let names = [];
    try {
      names = fs.readdirSync(dir);
    } catch {
      continue;
    }
    for (const name of names) {
      if (!name.endsWith(".task.json")) continue;
      out.push({ name, dir, done });
    }
  }
  return out;
}

// 同名文件在 done/ 里以 done 为准；文件被删/移走 => 视为已归档
function inboxIndex() {
  const idx = new Map();
  for (const it of scanInbox()) {
    const prev = idx.get(it.name);
    if (!prev || it.done) idx.set(it.name, it);
  }
  return idx;
}

function dialogRecordFromInboxTask(name, obj, done, mtime) {
  const raw = obj && typeof obj === "object" ? obj : {};
  // inbox 任务里的 instance/claimedBy 一律归一成看板名（历史文件里的 dsh-main/@dsh 照样认）
  const inst = boardName(raw.instance || raw.to || "dsh");
  const claimedBy = raw.claimedBy ? boardName(raw.claimedBy) : null;
  let body = String(raw.do || raw.objective || raw.why || "").trim();
  if (!body) body = clip(JSON.stringify(raw), 600);
  const ts = raw.ts
    ? String(raw.ts)
    : raw.createdAt
      ? toCst(new Date(raw.createdAt))
      : toCst(mtime);
  return {
    id: dialogIdFor("inbox|" + name),
    ts,
    from: boardName(raw.from || CODEX_SERVICE),
    to: inst,
    channel: "inbox",
    kind: "task",
    body: redact(clip(body, 1500)),
    threadId: null,
    refs: {
      inbox: name,
      dir: done ? "done" : "pending",
      instance: inst,
      claimedBy,
      target: raw.target || null,
      event: raw.event || null,
      link: "outputs/inbox/" + (done ? "done/" : "") + name,
    },
    state: done ? "done" : "dispatched",
  };
}

function ingestInboxTasks() {
  const keyI = statKey(INBOX_DIR) + "|" + statKey(INBOX_DONE_DIR);
  if (keyI && keyI === ingestCache.inbox) return 0;
  let n = 0;
  for (const it of scanInbox()) {
    let obj;
    let mtime = new Date();
    try {
      const file = path.join(it.dir, it.name);
      obj = JSON.parse(fs.readFileSync(file, "utf8"));
      mtime = fs.statSync(file).mtime;
    } catch {
      continue;
    }
    const rec = dialogRecordFromInboxTask(it.name, obj, it.done, mtime);
    if (rec && appendDialog(rec)) n++;
  }
  ingestCache.inbox = statKey(INBOX_DIR) + "|" + statKey(INBOX_DONE_DIR);
  return n;
}

// ————————————————————————————————————————————————
// 适配器（进）：桥信箱 → 标准记录
// messages/*.json = 双向邮件（report/message）；tasks/*.json = headless 任务（task）。
// 读不到（WSL 没起 / 权限）只记一次日志，不影响其它通道。
// ————————————————————————————————————————————————
const BRIDGE_KIND_MAP = { question: "message", request: "message", task: "task" };
let bridgeScanWarned = false;

function bridgeRecordFromMessage(m) {
  const raw = m && typeof m === "object" ? m : {};
  const mid = String(raw.id || "");
  if (!mid) return null;
  const sender = String(raw.sender || "").toLowerCase();
  const recipient = String(raw.recipient || "").toLowerCase();
  const rawKind = String(raw.kind || "message").toLowerCase();
  const parts = [];
  const body = redact(clip(raw.body, BRIDGE_BODY_MAX));
  if (body) parts.push(body);
  if (raw.progress) parts.push("[进度] " + redact(clip(raw.progress, 300)));
  if (raw.evidence) parts.push("[证据] " + redact(clip(raw.evidence, 300)));
  return {
    id: dialogIdFor("bridge-msg|" + mid),
    ts: raw.createdAt ? toCst(new Date(raw.createdAt)) : dialogTs(),
    from: sender ? boardName(sender) : String(raw.sender || "?"),
    to: recipient ? boardName(recipient) : "none",
    channel: "bridge",
    kind: BRIDGE_KIND_MAP[rawKind] || "report",
    body: parts.join("\n\n"),
    threadId: null,
    refs: {
      bridge: mid,
      bridgeKind: rawKind,
      rootTaskId: raw.rootTaskId || null,
      taskId: raw.taskId || null,
      replyTo: raw.replyTo || null,
      workspace: raw.workspace || null,
      link: ".dsh-codex-bridge/messages/" + mid + ".json",
    },
    // 收件人是 Codex 且未读 => 待办；自己发出去 / 已读 => done
    state: sender === "codex" || raw.readAt ? "done" : "open",
  };
}

function bridgeRecordFromTask(t) {
  const raw = t && typeof t === "object" ? t : {};
  const taskId = String(raw.taskId || "");
  if (!taskId) return null;
  const status = String(raw.status || "running").toLowerCase();
  const owner = String(raw.owner || "dsh").toLowerCase();
  let state = "open";
  if (status === "completed" || status === "cancelled" || status === "canceled") state = "done";
  else if (status === "failed" || status === "error") state = "failed";
  return {
    id: dialogIdFor("bridge-task|" + taskId),
    ts: raw.createdAt ? toCst(new Date(raw.createdAt)) : dialogTs(),
    from: CODEX_SERVICE,
    to: boardName(owner),
    channel: "bridge",
    kind: "task",
    body: redact(clip(raw.objective, 1500)),
    threadId: null,
    refs: {
      bridgeTask: taskId,
      rootTaskId: raw.rootTaskId || null,
      status,
      workspace: raw.workspace || null,
      link: ".dsh-codex-bridge/tasks/" + taskId + ".json",
    },
    state,
  };
}

function ingestBridgeMail() {
  const keyB = statKey(path.join(BRIDGE_DIR, "messages")) + "|" + statKey(path.join(BRIDGE_DIR, "tasks"));
  if (keyB && keyB === ingestCache.bridge) return 0;
  let n = 0;
  for (const [sub, make] of [
    ["messages", bridgeRecordFromMessage],
    ["tasks", bridgeRecordFromTask],
  ]) {
    const dir = path.join(BRIDGE_DIR, sub);
    let names;
    try {
      names = fs.readdirSync(dir);
    } catch (e) {
      if (!bridgeScanWarned) {
        bridgeScanWarned = true;
        log("BRIDGE SCAN SKIPPED:", e.code || e.message, dir);
      }
      continue;
    }
    for (const name of names) {
      if (!name.endsWith(".json")) continue;
      let obj;
      try {
        obj = JSON.parse(fs.readFileSync(path.join(dir, name), "utf8"));
      } catch {
        continue;
      }
      const rec = make(obj);
      if (rec && appendDialog(rec)) n++;
    }
  }
  if (n) log("BRIDGE INGEST records=" + n);
  ingestCache.bridge = statKey(path.join(BRIDGE_DIR, "messages")) + "|" + statKey(path.join(BRIDGE_DIR, "tasks"));
  return n;
}

// ————————————————————————————————————————————————
// 接单锁（读取时现算状态）
// - 文件已归档 / 已被删除 => done（回复自动消的主通道）
// - 该实例在派单之后回过帖 => done（回复自动消的副通道）
// - 超过 CLAIM_TIMEOUT_MS 仍无回应 => 待办
  // - 其余 => dispatched（已派单，等待接单执行）
  // ————————————————————————————————————————————————
// 呈现前先归一（**只在读取时归一，绝不重写历史行**）：
//   ① from/to → 看板名：历史行里的 “DSH / Codex / codex-convtool / dsh-main”
//      统一显示成同一串名字；
//   ② 正文里的任务号 → 新号（CT-021 → HUB-001 …）：表在 task_id_aliases.json，
//      **数据化 + 热加载**——以后再改号只改 json，不动代码、不重启服务。
// 旧卡“只标记不删”，所以旧号仍然查得到；但**界面上不再出现死号** —— 和署名归一同一个原则。
let taskIdAliasCache = { at: 0, map: {}, re: null };
function taskIdAliases() {
  if (Date.now() - taskIdAliasCache.at < 5000) return taskIdAliasCache.map;
  const map = {};
  try {
    const obj = JSON.parse(fs.readFileSync(TASK_ID_ALIAS_FILE, "utf8"));
    for (const [k, v] of Object.entries(obj.aliases || {})) {
      // 只收形如 HUB-001 的合法号，坏数据不许进管线
      if (/^[A-Z]{2,5}-\d{2,4}$/.test(k) && /^[A-Z]{2,5}-\d{2,4}$/.test(String(v))) map[k] = String(v);
    }
  } catch (e) {
    if (!taskIdAliasCache.at) log("TASK ID ALIAS FILE UNREADABLE (忽略):", e.message);
  }
  const keys = Object.keys(map).map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  taskIdAliasCache = {
    at: Date.now(),
    map,
    re: keys.length ? new RegExp("(" + keys.join("|") + ")(?!\\d)", "g") : null,
  };
  return map;
}
function normalizeTaskIds(text) {
  const s = text == null ? "" : String(text);
  if (!s) return s;
  taskIdAliases();
  const re = taskIdAliasCache.re;
  if (!re) return s;
  return s.replace(re, (m) => taskIdAliasCache.map[m] || m);
}
function normalizeRecordNames(r) {
  return { ...r, from: boardName(r.from), to: boardName(r.to), body: normalizeTaskIds(r.body) };
}

// 公告回执（老板 2026-09-11 02:1x 定的口径）：**不叫醒任何人**，等对方下次露面时自己带回执。
// 判定在读取时现算，不落新状态：公告之后，某条注册线（非公告作者）首次发帖里出现
// 「已阅 / 回执 / 收到」→ 记它已回执；否则算未回执。手机页就在公告卡片下面写一行浅色小字。
// 必须**行首显式**写「已阅」或「回执」才算回执——不然任何一句"收到/回执"都会误判成已读
// （刚上线时就把看板服务的一条回帖误判成了已回执）。
// ── 回执口径（**老板 2026-09-12 重做**："公告必须回复收到"、"已回执的也要回执"）──────────────
// 结论：**取消笼统式回执**——不许用一句"已阅"覆盖之前的公告；**每条公告都要单独回执**。
// 为了让"单独回"可行，每条公告有一个**短号**（如 `N-3F7A`），回执写：
//   ① `收到 N-3F7A`（推荐；短号来自公告记录 id 的稳定派生）
//   ② `收到 21:30`（点名时间，兼容老写法）
//   ③ **引用回复那条公告**（点「↩ 引用」再回"收到"）——最自然，按 refs.quote.id 计
// 裸词（`收到` / `已阅` 后面什么都没有）**不计**，因为分不清是回哪一条。
const ACK_WORDS = "(?:收到|已阅|回执)";
const ACK_RE = new RegExp("(?:^|\\n)\\s*" + ACK_WORDS + "\\s*[:：]?\\s*(N-[0-9A-Z]{4}|[0-2]?\\d:[0-5]\\d)?", "g");
function noticeCode(id) {
  return "N-" + String(id || "").slice(0, 4).toUpperCase();
}
// 公告有效期：过期就不再要求回执（"有些公告已经失效了，自然不必存在"）。默认 24 小时。
const NOTICE_TTL_MS = Number(process.env.MCHAT_NOTICE_TTL_MS || 24 * 3600 * 1000);
// ── 公告"送到"的记账（HUB-015，`codex-修复` 2026-09-13 01:54 反馈）────────────────
//   每条线对每条公告的**投递时刻**：回执计时从"投递给它的那一刻"起算，而不是从公告发布时间起算。
//   为什么：新号入职后**仍要**对生效公告回执（老板已定性的好特性），但它的 24h 窗口应该是
//   "从它收到那一刻"开始——否则"入职晚于发布"就成了事实豁免，等于新人天然不用回执。
function noticeDeliveryMap() {
  try {
    return readState().noticeDeliveredAt || {};
  } catch {
    return {};
  }
}
function markNoticeDelivered(id, aliases) {
  const list = (Array.isArray(aliases) ? aliases : [aliases]).filter(Boolean);
  if (!id || !list.length) return 0;
  try {
    const st = readState();
    const map = { ...(st.noticeDeliveredAt || {}) };
    const now = Date.now();
    for (const a of list) map[String(id) + "|" + a] = now;
    writeState({ ...readState(), noticeDeliveredAt: map });
    return list.length;
  } catch {
    return 0;
  }
}
function applyNoticeAcks(records) {
  // 谁**必须**回执？= 在册的员工线。剔除三类"不是员工"的条目：
  //   ① 退役档案条目（`·退役` / status=retired）② 系统角色 codex-看板服务 ③ 自测身份 codex-看板助理
  //   （它们要么没有会话、要么不是人，列在"未收到"里是永久噪声）
  const NON_EMPLOYEE = new Set([CODEX_SERVICE, "codex-看板助理"]);
  const allAgents = readAgents().agents || {};
  const agents = Object.keys(allAgents).filter((a) => {
    if (NON_EMPLOYEE.has(a) || /·退役$/.test(a)) return false;
    const m = allAgents[a] || {};
    return String(m.status || "").toLowerCase() !== "retired";
  });
  // HUB-015(c)：**在册但没 threadId** 的条目不进"该回执"名单——它们本来就收不到
  // （投递按名册寻址，没 threadId 直接 no-thread），列进去只会每次公告固定产生 2 次空催 + 1 行噪声
  // （现场：dsh-老员工 / dsh-quant，板上 09-12 23:17、23:27 那两行）。它们**仍可回执、仍会被记账**。
  const reachable = agents.filter((a) => !!(allAgents[a] || {}).threadId);
  // 每条线对每条公告的投递时刻（HUB-015(b)）
  const deliveredMap = noticeDeliveryMap();
  const notices = records.filter((r) => r.kind === "notice").sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
  if (!notices.length) return records;
  // "回执在这条公告之后" 用**记录顺序**判，不用时间戳：看板行是**分钟精度**，
  // 同一分钟内"公告先、回执后"用 ts 比会被判成"在公告之前"（自测当场抓到）。
  const orderIdx = new Map(records.map((r, i) => [String(r.id), i]));
  const out = new Map();
  // 取代关系：同一天 + 同一作者 → 后一条取代前一条（"新公告以新的为准"）
  const lastByAuthorDay = new Map();
  for (const n of notices) {
    const key = String(n.ts).slice(0, 10) + "|" + String(n.from);
    const prev = lastByAuthorDay.get(key);
    if (prev) out.set(prev.id, { ...(out.get(prev.id) || {}), supersededBy: n.ts, supersededById: n.id });
    lastByAuthorDay.set(key, n);
  }
  for (const n of notices) {
    const nTs = parseCst(n.ts);
    const nIdx = orderIdx.get(String(n.id));
    const acks = {};
    for (const r of records) {
      if (r.kind === "notice") continue;
      const rIdx = orderIdx.get(String(r.id));
      // 顺序优先；顺序不可得时退回时间比较
      if (nIdx != null && rIdx != null ? rIdx <= nIdx : parseCst(r.ts) <= nTs) continue;
      const from = String(r.from || "");
      if (!agents.includes(from) || from === n.from) continue;
      // ① 引用回复这条公告 → 直接算回执（最自然："点引用 → 回收到"）
      const quoted = r.refs && r.refs.quote && String(r.refs.quote.id || "") === String(n.id);
      // ② 正文里出现 `收到 <短号>` 或 `收到 <时间>`（**必须带指向**，裸词不算）
      const body = String(r.body || "");
      const mentions = [...body.matchAll(new RegExp(ACK_RE.source, "g"))];
      const code = noticeCode(n.id);
      const codes = mentions.filter((x) => x[1] && /^N-/.test(x[1])).map((x) => String(x[1]).toUpperCase());
      const points = mentions.filter((x) => x[1] && !/^N-/.test(x[1])).map((x) => String(x[1]).padStart(5, "0"));
      const byCode = codes.includes(code);
      const byTime = points.includes(String(n.ts).slice(11, 16));
      if (!acks[from] && (quoted || byCode || byTime)) {
        acks[from] = { ts: r.ts, mode: quoted ? "quote" : byCode ? "code" : "point" };
      }
    }
    out.set(n.id, { ...(out.get(n.id) || {}), acks });
  }
  const now = Date.now();
  return records.map((r) => {
    if (r.kind !== "notice") return r;
    const info = out.get(r.id) || {};
    const acks = info.acks || {};
    const expected = reachable.filter((a) => a !== r.from);
    const nTs = parseCst(r.ts);
    const expired = now - nTs > NOTICE_TTL_MS;
    const supersededBy = info.supersededBy || null;
    // HUB-015(b)：逐线窗口——起点 = **投递给它的时刻**，没记到就退回公告发布时间
    const windowOk = (a) => {
      const base = Number(deliveredMap[String(r.id) + "|" + a] || 0) || nTs;
      return now - base <= NOTICE_TTL_MS;
    };
    const pendingAck = supersededBy ? [] : expected.filter((a) => !acks[a] && windowOk(a));
    // 显示口径：公告本身没过期，**或者**它虽然全局过期、但还有线在"自己的窗口"里（刚入职的新号）
    const active = !supersededBy && (!expired || pendingAck.length > 0);
    return {
      ...r,
      refs: {
        ...(r.refs || {}),
        acks,
        expected,
        pendingAck,
        expired,
        supersededBy,
        active,
      },
    };
  });
}

// ── 公告催办（2026-09-12）："必须回复收到"就得有人催 ─────────────────────────
//   每 10 分钟扫一次：生效中的公告 × 尚未回执的线 → 投一条催办（带短号）；
//   同一条公告同一条线**最多催 2 次**（记在 state.noticeNudge），催满仍未回 → 上板一行汇总。
//   限流靠 deliverByQueue（90 秒冷却 + 每小时上限），不另设闸门。
const NOTICE_NUDGE_MS = Number(process.env.MCHAT_NOTICE_NUDGE_MS || 10 * 60 * 1000);
const NOTICE_NUDGE_MAX = Number(process.env.MCHAT_NOTICE_NUDGE_MAX || 2);
async function noticeNudgeTick() {
  if (busy || haltActive()) return;
  let records;
  try {
    records = applyNoticeAcks(readDialog(600).map(normalizeRecordNames));
  } catch {
    return;
  }
  const st = readState();
  const nudges = { ...(st.noticeNudge || {}) };
  const now = Date.now();
  let nudged = 0;
  for (const n of records.filter((r) => r.kind === "notice" && r.refs && r.refs.active)) {
    const code = noticeCode(n.id);
    const times = nudges[n.id] || {};
    if (now - parseCst(n.ts) < NOTICE_NUDGE_MS) continue; // 刚发的先给人留时间
    for (const alias of n.refs.pendingAck || []) {
      const done = Number(times[alias] || 0);
      if (done >= NOTICE_NUDGE_MAX) continue;
      const last = Number((st.noticeNudgeAt || {})[n.id + "|" + alias] || 0);
      if (now - last < NOTICE_NUDGE_MS) continue;
      const dv = await deliverByQueue(alias, "（催办 · 公告 " + code + "）你还没回执。请在看板回一行：收到 " + code + "（或引用那条公告回「收到」）。").catch(() => ({ ok: false }));
      times[alias] = done + 1;
      nudges[n.id] = times;
      const atAll = { ...(readState().noticeNudgeAt || {}) };
      atAll[n.id + "|" + alias] = now;
      writeState({ ...readState(), noticeNudge: nudges, noticeNudgeAt: atAll });
      nudged++;
      if (times[alias] >= NOTICE_NUDGE_MAX && !dv.ok) {
        appendBoardLine("老板", CODEX_SERVICE, "（系统：公告 " + code + " 催 " + NOTICE_NUDGE_MAX + " 次仍未收到 @" + alias + " 的回执——它可能不在场；回来后会看到信箱里的公告。）");
      }
      break; // 一轮只催一条，别刷屏
    }
  }
  if (nudged) log("NOTICE NUDGE:", nudged);
}

// ══════════════════════════════════════════════════════════════
// HUB-003 向上敲门铃（**降级版**，老板 2026-09-11 05:5x 拍板："叫不到就叫不到呗"）
//   四件门铃：① 凡"待老板"一律**上板并 @老板**（不许只压信箱）
//             ② 手机页**置顶一行「待老板：N 条」**（一眼看到"要他做什么"）
//             ③ 页面内提醒（标题闪烁）——**只在页面开着时有效，文案必须诚实**
//             ④ 系统推送 = 将来项；升级触发条件：出现一次"因没及时看到而误事"
//   只推三类事件；每条必须带"要你做什么"（没有动作的一律不发）；同任务 10 分钟只推一次；
//   每日上限；可静音（**事件仍入记录、仍上板，不丢**）；可追溯（落盘 + 老板发话即视为看到）。
//   平台前提已实测写进卡里：`isSecureContext=false` → 没有 Service Worker → Web Push 做不到。
// ══════════════════════════════════════════════════════════════
const BOSS_EVENT_FILE = path.join(STATE_DIR, "boss_events.ndjson");
const BOSS_KINDS = { accept: "待验收", decide: "需拍板", incident: "故障" };
const BOSS_THROTTLE_MS = Number(process.env.MCHAT_BOSS_THROTTLE_MS || 10 * 60 * 1000);
const BOSS_DAILY_MAX = Number(process.env.MCHAT_BOSS_DAILY_MAX || 20);

// ══════════════════════════════════════════════════════════════
// HUB-007 实时通道（SSE）+ HUB-008 任务/项目接口
//   ① `/api/events`：**不要求 token、不带数据**，只推"变了"这个事实（真源仍走 REST）；
//   ② `/api/tasks`：把"任务卡(docs/tasks/*.md) + inbox 派单"合成**一张任务表**，按前缀分组当项目；
//   ③ `POST /api/tasks`：建卡（自动取号、落标准模板、投信箱、看板留痕、尽力唤醒）；
//   ④ `POST /api/tasks/status`：状态流转写**侧车**（不改卡；卡是规范真源，运行态是投影）。
// ══════════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════════
// HUB-012 承载层：员工 / 物料·节点（时间轴）/ 多来源归一
//   定位（老板 2026-09-12 01:4x）：**套件是真实的"员工工厂"（真源在 D:\agent_crew_kits），
//   App 是"承载层"**——不复制真源，只读它、投影它；App 自己新增的（项目物料/群组/暂停/已读）
//   一律 append-only + 带 id/ts/from（对齐套件 I1/I2）。
// ══════════════════════════════════════════════════════════════
const KIT_DIR = process.env.MCHAT_KIT_DIR || "D:\\agent_crew_kits";
function kitCards() {
  const out = [];
  try {
    for (const n of fs.readdirSync(path.join(KIT_DIR, "agents"))) {
      if (!n.endsWith(".card.json")) continue;
      try {
        out.push(JSON.parse(fs.readFileSync(path.join(KIT_DIR, "agents", n), "utf8")));
      } catch {}
    }
  } catch {}
  return out;
}
function kitStates() {
  const out = {};
  try {
    for (const d of fs.readdirSync(path.join(KIT_DIR, ".private"))) {
      try {
        const s = JSON.parse(fs.readFileSync(path.join(KIT_DIR, ".private", d, "state.json"), "utf8"));
        if (s && s.slug) out[s.slug] = s;
      } catch {}
    }
  } catch {}
  return out;
}
// 员工视图 = 套件员工卡（真源）+ 套件运行态 + 本 Hub 运行态
function buildEmployees() {
  const cfg = readAgents().agents || {};
  const states = kitStates();
  const bySlug = {};
  const byName = {};
  for (const [alias, meta] of Object.entries(cfg)) {
    if (meta && meta.slug) bySlug[meta.slug] = alias;
    byName[alias] = alias;
  }
  const out = [];
  const seen = new Set();
  const push = (card) => {
    const slug = String(card.slug || "");
    const alias = bySlug[slug] || (card.name && byName[card.name]) || String(card.name || slug);
    const meta = cfg[alias] || {};
    const st = states[slug] || {};
    const lastSeenTs = lastOwnStatementTs(alias, readDialog(0));
    out.push({
      alias: alias,
      slug: slug,
      kind: card.kind || "",
      level: card.level || meta.level || st.level || "member",
      role: card.role || st.role || meta.title || "",
      owner: card.owner || "老板",
      persona: card.persona || null,
      permissions: card.permissions || [],
      slots: card.slots || [],
      capabilities: card.capabilities || null,
      duty: dutyEnabled(alias),
      status: st.status || "unknown",
      currentTask: st.currentTask || "",
      nextAction: st.nextAction || "",
      blockers: st.blockers || [],
      workspace: card.workspace || meta.workspace || "",
      threadId: meta.threadId || null,
      pendingMail: pendingMailFor(alias, lastSeenTs),
      lastSeen: lastSeenTs,
      avatar: avatarOf(alias),
      source: "kit-card" + (st.status ? "+state" : ""),
    });
    seen.add(slug);
    seen.add(alias);
  };
  for (const c of kitCards()) push(c);
  // 套件里没有卡的线（本仓自建/历史线）也要能看到，否则"状态栏少人"
  for (const [alias, meta] of Object.entries(cfg)) {
    if (seen.has(alias) || seen.has(meta.slug)) continue;
    push({ name: alias, slug: meta.slug, level: meta.level || "member", role: meta.title || "", workspace: meta.workspace || "" });
  }
  return out.sort((a, b) => String(a.alias).localeCompare(String(b.alias)));
}
// 项目物料 / 节点：时间轴上的东西（文档、交付物、里程碑、归档…）
const ITEMS_FILE = path.join(STATE_DIR, "items.ndjson");
const ITEM_KINDS = ["material", "node", "doc", "archive", "note"];
function readItems(limit) {
  try {
    const rows = fs
      .readFileSync(ITEMS_FILE, "utf8")
      .split("\n")
      .filter(Boolean)
      .map((l) => {
        try {
          return JSON.parse(l);
        } catch {
          return null;
        }
      })
      .filter(Boolean);
    return limit > 0 ? rows.slice(-limit) : rows;
  } catch {
    return [];
  }
}
function appendItem(it) {
  try {
    fs.appendFileSync(ITEMS_FILE, JSON.stringify(it) + "\n", "utf8");
    sseNotify("items");
    return true;
  } catch (e) {
    log("ITEM WRITE FAILED:", e.message);
    return false;
  }
}

// ══════════════════════════════════════════════════════════════
// HUB-011 可塑性：为"将来做成 App"留接口余地（老板 2026-09-12 01:3x）
//   原则：**客户端只依赖 REST + SSE，不依赖页面**；服务端不假设"客户端是网页"。
//   本轮补：① `/api/meta` 版本与能力协商；② `/api/dialog` 增量游标（since/before）；
//           ③ 服务端已读位置（多设备同步的地基）；④ 各数据文件带 schema 版本。
// ══════════════════════════════════════════════════════════════
const API_VERSION = "2";              // 接口大版本（客户端据此协商；只加不改）
const SERVER_VERSION = "board.mjs/0.12"; // 服务端自身版本（与 PAGE_VER 解耦）
const READ_STATE_FILE = path.join(STATE_DIR, "read_state.json");
function readReadState() {
  try {
    const o = JSON.parse(fs.readFileSync(READ_STATE_FILE, "utf8"));
    return o && o.devices ? o : { schema: 1, devices: {} };
  } catch {
    return { schema: 1, devices: {} };
  }
}
function writeReadState(o) {
  try {
    fs.writeFileSync(READ_STATE_FILE, JSON.stringify(o, null, 2), "utf8");
  } catch (e) {
    log("READ STATE WRITE FAILED:", e.message);
  }
}
// 服务端能力清单：**客户端拿这个决定用什么**（而不是猜服务端有没有某个口）
function capabilities() {
  return {
    apiVersion: API_VERSION,
    serverVersion: SERVER_VERSION,
    pageVersion: PAGE_VER,
    features: [
      "sse:/api/events",
      "dialog.cursor:since,before",
      "dialog.readState",
      "tasks:get,post,status",
      "groups:get,post",
      "contacts:get",
      "halt:get,post",
      "bossEvents:post",
      "mail:post",
      "bind:post",
      "onboard:post",       // HUB-001 入职：给新线发牌（工号永不复用 / 会话唯一 / 必须写批准人）
      "avatars:derived",
    ],
    schemas: {
      dialog: "dialog.v1",
      inboxTask: "dialog.v1",
      agents: "agents.v3",
      groups: "groups.v1",
      halt: "halt.v1",
      tasksState: "tasks_state.v1",
      readState: "read_state.v1",
      bossEvents: "boss_events.v1",
    },
    transports: ["http+json", "sse"],
    auth: ["x-mchat-token", "query:token(/api/events 不需要)"],
    // HUB-004 派单表单：下拉的候选一律由服务端给，页面不写死（不然登记表一改就漂）
    taskPrefixes: TASK_PREFIXES,
    taskKinds: TASK_KINDS,
    taskPrios: TASK_PRIOS,
    // slug 跨系统契约（唯一规范：套件仓 docs/slug.md）。把锚点**算出来**给对面，
    // 谁改了算法都能一眼看出来（总监 2026-09-13：对不上就给他两边样例）。
    slugContract: {
      spec: "agent_crew_kits/docs/slug.md",
      rule: "显式优先 → 兜底 side + '-' + sha1(看板名,UTF-8)[0:6]（side=名'-'前那段，只认 dsh/codex，其余 x） → 老板=boss",
      anchors: {
        "codex-套件": makeSlug("codex-套件"),
        "dsh-老员工": makeSlug("dsh-老员工"),
        "codex-甲": makeSlug("codex-甲"),
        "codex-乙": makeSlug("codex-乙"),
        "老板": makeSlug("老板"),
      },
    },
    limits: { dialogDefaultLimit: 200, dialogMaxLimit: 500, sseHeartbeatSec: 20 },
  };
}

// ══════════════════════════════════════════════════════════════
// HUB-010 群组（微信式顶部群组 + 注入接口）
//   老板 2026-09-12 01:0x："做成和微信一样的，上面有群组…但是通过添加按钮添加的…
//   我让总监把生成的数据格式做个中间件，然后注入进去就行了，弄个接口。"
//   契约：`POST /api/groups {name, members[], note?, by, source?}` —— **幂等 upsert**，
//   外部的中间件（总监那边）可以反复注入；`removed:true` 只标记不物理删。
// ══════════════════════════════════════════════════════════════
const GROUPS_FILE = path.join(STATE_DIR, "groups.json");
function readGroups() {
  try {
    const o = JSON.parse(fs.readFileSync(GROUPS_FILE, "utf8"));
    return o && o.groups ? o : { schema: 1, groups: {} };
  } catch {
    return { schema: 1, groups: {} };
  }
}
function writeGroups(o) {
  try {
    fs.writeFileSync(GROUPS_FILE, JSON.stringify(o, null, 2), "utf8");
    sseNotify("groups");
  } catch (e) {
    log("GROUPS WRITE FAILED:", e.message);
  }
}
function groupIdOf(name) {
  const s = String(name || "").trim();
  const ascii = s.replace(/[^A-Za-z0-9_-]/g, "");
  if (ascii && ascii.length === s.length) return "g-" + ascii.toLowerCase();
  return "g-" + crypto.createHash("sha1").update(s).digest("hex").slice(0, 6);
}
function listGroups(includeRemoved) {
  const g = readGroups().groups;
  return Object.values(g)
    .filter((x) => includeRemoved || !x.removed)
    .sort((a, b) => String(a.name).localeCompare(String(b.name)));
}

// ── HUB-013 退役工号（承接/换人）──────────────────────────────────────────────
// 口径（与 codex-总监 2026-09-12 对齐）：**岗位名延续（同名即现任）· 工号(slug)换代永不复用**。
//   · @<看板名>       → 投给**现任**（岗位延续）
//   · @<旧 slug>      → **不再作为投递目标**：明确回一句"旧工号已退役，请用岗位名"，
//                       而不是静默写进一个不存在线的信箱（那就是静默丢）
function retiredSlugOwner(tok) {
  const t = String(tok || "").trim().replace(/^@/, "");
  if (!t) return "";
  const cfg = readAgents();
  const agents = cfg.agents || {};
  // 现任看板名 / 现任 slug / 内部别名 → 正常，不拦
  if (agents[t] || boardName(t) !== t) return "";
  for (const meta of Object.values(agents)) {
    if (String(meta.slug || "") === t) return ""; // 某个现任条目的 slug
  }
  // 旧 slug：显式别名表，或退役条目的 slug，或 failedThreadIdsOwner?（只认 slug）
  const aliases = cfg.slugAliases || {};
  if (aliases[t]) return String(aliases[t]);
  for (const [alias, meta] of Object.entries(agents)) {
    if (String(meta.status || "").toLowerCase() === "retired" && String(meta.slug || "") === t) return alias;
  }
  return "";
}

// 头像：**由看板名稳定派生**（同一个名字永远同一个头像；不存文件、不用外链）。
// 前端只拿到 {text, hue} 自己画一个圆——保持现有配色与圆角风格。
function avatarOf(alias) {
  const s = String(alias || "?");
  const short = s.replace(/^(dsh|codex)-/, "");
  const m = short.match(/[A-Za-z0-9\u4e00-\u9fa5]/);
  const text = (m ? m[0] : "?").toUpperCase();
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return { text: text, hue: h };
}

const sseClients = new Set();
function sseNotify(kind) {
  if (!sseClients.size) return;
  const msg = "event: changed\ndata: " + JSON.stringify({ kind: kind || "changed", at: Date.now() }) + "\n\n";
  for (const c of [...sseClients]) {
    try {
      c.write(msg);
    } catch {
      sseClients.delete(c);
    }
  }
}
// 任务卡目录：真源在仓库 docs/tasks/；给 env 覆盖是为了**自测隔离**（不然测试会往真仓库写卡）
const TASKS_DIR = process.env.MCHAT_TASKS_DIR || path.join(WORKSPACE, "docs", "tasks");
const TASKS_STATE_FILE = path.join(STATE_DIR, "tasks_state.json");
const TASK_PREFIXES = ["HUB", "KIT", "TRD", "NET", "DAT"]; // 真源 docs/TASK_ID_STANDARD.md §二
// HUB-004 派单表单用：类型 / 优先级清单。页面**从 /api/meta 取**，不写死在页面里。
const TASK_KINDS = ["incident", "dev", "debug", "test", "ops"];   // 卡 §二
const TASK_PRIOS = ["P0", "P1", "P2", "P3"];                      // 卡 §二
const TASK_STATES = ["open", "claimed", "blocked", "done", "dropped"];
function readTasksState() {
  try {
    const o = JSON.parse(fs.readFileSync(TASKS_STATE_FILE, "utf8"));
    return o && o.tasks ? o.tasks : o; // 兼容老格式（直接是 map）
  } catch {
    return {};
  }
}
function writeTasksState(o) {
  try {
    // 带 schema 版本写入（老格式读端已兼容）
    fs.writeFileSync(TASKS_STATE_FILE, JSON.stringify({ schema: "tasks_state.v1", tasks: o }, null, 2), "utf8");
    sseNotify("tasks");
  } catch (e) {
    log("TASKS STATE WRITE FAILED:", e.message);
  }
}
function parseTaskCard(name, text) {
  const id = String(name).replace(/\.md$/, "");
  const s = String(text || "");
  const lines = s.split("\n");
  const head = (lines.find((l) => /^#\s+/.test(l)) || "").replace(/^#\s+/, "").trim();
  const title = head.replace(new RegExp("^" + id + "\\s*"), "").trim() || head;
  const kind = (s.match(/类型\*{0,2}：\s*`?([a-zA-Z]+)`?/) || [])[1] || "";
  const assignee = ((s.match(/接手：\s*`?([^`\n]+?)`?\s*$/m) || [])[1] || "").trim();
  const cardDropped = /作废|已移交/.test(lines.slice(0, 10).join(" "));
  return { id: id, title: title, kind: kind, assignee: assignee, project: (id.split("-")[0] || "").toUpperCase(), cardDropped: cardDropped };
}
function listTaskCards() {
  try {
    return fs
      .readdirSync(TASKS_DIR)
      .filter((n) => n.endsWith(".md"))
      .map((n) => parseTaskCard(n, fs.readFileSync(path.join(TASKS_DIR, n), "utf8")));
  } catch {
    return [];
  }
}
// 统一的"任务表"：卡（规范真源）+ 派单（运行态）
function buildTaskTable() {
  const st = readTasksState();
  const out = [];
  for (const c of listTaskCards()) {
    const s = st[c.id] || {};
    const state = s.state || (c.cardDropped ? "dropped" : "open");
    out.push({
      id: c.id,
      title: c.title,
      kind: c.kind,
      assignee: c.assignee,
      project: c.project,
      state: state,
      by: s.by || "",
      at: s.at || "",
      note: s.note || "",
      source: "card",
      file: "docs/tasks/" + c.id + ".md",
      updatedAt: s.at || "",
    });
  }
  for (const it of scanInbox()) {
    let obj = {};
    try {
      obj = JSON.parse(fs.readFileSync(path.join(it.dir, it.name), "utf8"));
    } catch {}
    const inst = boardName(obj.instance || obj.to || "dsh");
    out.push({
      id: it.name.replace(/\.task\.json$/, ""),
      title: String(obj.do || obj.objective || obj.why || it.name).slice(0, 80),
      kind: obj.kind || "dispatch",
      assignee: inst,
      project: (/^board_/.test(it.name) ? "转投" : "派单"),
      state: it.done ? "done" : "claimed",
      by: boardName(obj.from || CODEX_SERVICE),
      at: obj.ts || "",
      note: "",
      source: it.done ? "inbox:done" : "inbox",
      file: "outputs/inbox/" + (it.done ? "done/" : "") + it.name,
      updatedAt: "",
    });
  }
  const byProject = {};
  for (const t of out) byProject[t.project] = (byProject[t.project] || 0) + 1;
  const byState = {};
  for (const t of out) byState[t.state] = (byState[t.state] || 0) + 1;
  return { count: out.length, byProject: byProject, byState: byState, tasks: out };
}
// 取号：该前缀下 max+1（不跳号、不复用；真源 docs/TASK_ID_STANDARD.md §三）
function nextTaskId(prefix) {
  let max = 0;
  for (const c of listTaskCards()) {
    const m = String(c.id).match(new RegExp("^" + prefix + "-(\\d{3})$"));
    if (m) max = Math.max(max, Number(m[1]));
  }
  for (const k of Object.keys(readTasksState())) {
    const m = String(k).match(new RegExp("^" + prefix + "-(\\d{3})$"));
    if (m) max = Math.max(max, Number(m[1]));
  }
  return prefix + "-" + String(max + 1).padStart(3, "0");
}
function taskCardTemplate(t) {
  return [
    "# " + t.id + " " + t.title,
    "",
    "- 派单人：" + t.author + "　接手：`" + t.assignee + "`",
    "- **类型**：`" + t.kind + "`　**优先级**：`" + t.priority + "`" + (t.due ? "　**截止**：" + t.due : ""),
    "- 范围：" + (t.scope || "见任务要求"),
    "- 关联：`outputs/dialog/pending_*.ndjson`（本单派到接手方信箱）",
    "",
    "## 一、目标",
    "",
    t.goal || t.title,
    "",
    "## 二、验收标准（逐条可判定）",
    "",
    ...t.acceptance.map((a, i) => (i + 1) + ". " + a),
    "",
    "## 三、签字区",
    "",
    "| 谁 | 何时 | 结论 | 证据 |",
    "| --- | --- | --- | --- |",
    "| （待本尊签） | | | |",
    "",
  ].join("\n");
}

// ══════════════════════════════════════════════════════════════
// HUB-006 暂停闸：**故障即停，停到老板看到**（老板 2026-09-11 05:5x 定调；卡 docs/tasks/HUB-006.md）
//   触发：S1/S2 或任何涉及钱的异常（S3/S4 不停）
//   停：自动派活 / 自动唤醒 / 一切涉及钱的自动动作
//   不停：已跑着的盯盘·数据同步·常驻引擎 / 取证 / 报告（否则"暂停"本身就是新故障）
//   状态是**有状态**的：`outputs/dialog/halt.json` + 看板红条 + 各线开工自检读它
//   解除 = **老板的公告**（`@全体` + 以 `【解除暂停】` 开头）——任何线不得自行解除
//   诚实口径：当前通道下"大家都会收到"= **"大家下次上场时都会看到"**，不许写"已通知全员"
// ══════════════════════════════════════════════════════════════
const HALT_FILE = path.join(STATE_DIR, "halt.json");
const HALT_REPEAT_MS = Number(process.env.MCHAT_HALT_REPEAT_MS || 30 * 60 * 1000);
function readHalt() {
  try {
    const h = JSON.parse(fs.readFileSync(HALT_FILE, "utf8"));
    return h && typeof h === "object" ? h : { halted: false };
  } catch {
    return { halted: false };
  }
}
function writeHalt(h) {
  try {
    fs.writeFileSync(HALT_FILE, JSON.stringify(h, null, 2), "utf8");
    sseNotify("halt"); // 暂停/恢复要立刻反映到每一块屏
  } catch (e) {
    log("HALT WRITE FAILED:", e.message);
  }
}
function haltActive() {
  return !!readHalt().halted;
}
function setHalt(by, severity, reason, taskId) {
  const h = {
    schema: "halt.v1",
    halted: true,
    since: toCst(new Date()),
    severity: severity || "",
    reason: reason || "",
    taskId: taskId || "",
    by: by || CODEX_SERVICE,
    lastRemindAt: Date.now(),
  };
  writeHalt(h);
  appendBoardLine("老板", CODEX_SERVICE,
    "【已暂停 · 等老板】" + (h.severity ? h.severity + " " : "") + (h.reason || "（未写原因）") +
    " · 要你做什么：处理完发一条 `@全体` 公告、**以【解除暂停】开头**即可恢复（只有你本人发的才算）。");
  log("HALT SET:", h.severity, h.reason.slice(0, 60), "by=" + h.by);
  return h;
}
function clearHalt(by, evidence) {
  const prev = readHalt();
  const now = toCst(new Date());
  writeHalt({ ...prev, halted: false, resumedAt: now, resumedBy: by, evidence: evidence || "" });
  appendBoardLine("老板", CODEX_SERVICE,
    "【已恢复 · 老板 " + String(now).slice(11, 16) + "】" + (evidence ? "依据：" + evidence + "。" : "") +
    "公告已投各线信箱；**各线下次上场时都会看到**（唤醒是尽力而为，等 HUB-005 通道全通才叫立刻全员）。");
  log("HALT CLEARED by", by, evidence || "");
  // 把"恢复"公告投各线信箱 + 尽力叫醒（限流/冷却照旧）
  const msg = "（看板公告·恢复）老板已解除暂停：" + String(now).slice(11, 16) + "。可以继续干活了。";
  for (const alias of Object.keys(readAgents().agents || {})) {
    if (alias === "老板") continue;
    try {
      fs.appendFileSync(
        path.join(MAILBOX_DIR, "pending_" + slugFor(alias) + ".ndjson"),
        JSON.stringify({ ts: fmtNow(), from: "老板", to: alias, body: msg }) + "\n",
        "utf8"
      );
    } catch {}
    deliverByQueue(alias, msg).catch(() => {});
  }
  return readHalt();
}

function readBossEvents() {
  try {
    return fs
      .readFileSync(BOSS_EVENT_FILE, "utf8")
      .split("\n")
      .filter((l) => l.trim())
      .map((l) => {
        try {
          return JSON.parse(l);
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  } catch {
    return [];
  }
}
function appendBossEvent(ev) {
  try {
    fs.appendFileSync(BOSS_EVENT_FILE, JSON.stringify(ev) + "\n", "utf8");
    sseNotify("boss"); // 置顶「待老板」也要秒到
    return true;
  } catch (e) {
    log("BOSS EVENT WRITE FAILED:", e.message);
    return false;
  }
}
function bossTodayCount(events) {
  const day = String(toCst(new Date())).slice(0, 10);
  return events.filter((e) => String(e.ts || "").slice(0, 10) === day).length;
}
// "老板看到了"的判定：**他在看板发过话就算看到**——不另设已读按钮，别让他多点一次。
// 判定用**序号/标记**而不是时间戳：看板行是分钟精度，同分钟内"事件先、发话后"根本分不出来
// （自测就抓到过这个 tie：事件和老板回话同一分钟 → 永远清不掉）。所以每条事件记下
// **创建那一刻最后一条老板记录的 id**；只要老板又发言（id 变了），这条就算看到了。
function lastBossRecordId(records) {
  let id = "";
  for (const r of records) {
    if (String(r.from) === "老板") id = String(r.id || "");
  }
  return id;
}
function bossPending(events, records) {
  const mark = lastBossRecordId(records);
  // 还没被看到的 = 创建时的标记**仍然等于**当前最后一条老板记录（说明他这之后没发过话）
  return events.filter((e) => String(e.ackMark || "") === mark);
}

function applyClaimStates(records) {
  const idx = inboxIndex();
  const latestFrom = new Map();
  for (const r of records) {
    const a = String(r.from || "").toLowerCase();
    if (!a || a === "codex" || a === "老板") continue;
    const cur = latestFrom.get(a);
    if (!cur || String(r.ts) > cur) latestFrom.set(a, String(r.ts));
  }
  const now = Date.now();
  return records.map((r) => {
    if (r.kind === "progress") return r;
    const refs = r.refs || {};
    const alias = String(r.to || "").toLowerCase();
    const claimedBy = String(refs.claimedBy || refs.instance || alias || "").toLowerCase() || null;
    let state = r.state;
    let overdue = false;
    const replied = alias && latestFrom.has(alias) && latestFrom.get(alias) > String(r.ts);
    if (refs.inbox && r.kind === "task") {
      const f = idx.get(String(refs.inbox));
      if (!f || f.done) state = "done";
      else if (replied) state = "done";
      else if (now - parseCst(r.ts) > CLAIM_TIMEOUT_MS) {
        state = "待办";
        overdue = true;
      } else state = "dispatched";
    } else if (r.channel === "bridge") {
      if (state === "open") {
        if (now - parseCst(r.ts) > CLAIM_TIMEOUT_MS) {
          state = "待办";
          overdue = true;
        }
      } else if (r.kind === "task" && state !== "done" && state !== "failed") {
        state = "待办";
        overdue = true;
      }
    }
    return { ...r, state, overdue, claimedBy };
  });
}

function initialDialogImport() {
  const st = readState();
  if (st.hubIngestOffset != null) return;
  try {
    const full = fs.readFileSync(BOARD_FILE, "utf8");
    const n = ingestBoardText(full);
    writeState({ ...readState(), hubIngestOffset: full.length });
    log("HUB initial import records=" + n);
  } catch (e) {
    log("HUB initial import failed:", e.message);
  }
}

function dialogContextText(n = DIALOG_CTX_N) {
  return readDialog(500)
    .filter((r) => r.kind !== "progress")
    .slice(-n)
    .map((r) => "[" + String(r.ts || "").slice(5, 16) + "] " + r.from + "->" + r.to + "(" + r.kind + "): " + r.body)
    .join("\n");
}

// 实例表 = 手机页状态栏芯片的真源；名字必须与 docs/BOARD_NAMES.md 逐字一致。
// schema 变了就重写（旧文件先备份成 agents.json.bak），这样命名规约能自动化落地。
const AGENTS_SCHEMA = 3;
function defaultAgents() {
  return {
    schema: AGENTS_SCHEMA,
    doc: "docs/BOARD_NAMES.md",
    primary: DSH_PRIMARY,
    agents: {
      "dsh-老员工": {
        label: "dsh-老员工",
        title: "老员工",
        slug: "dsh-main",
        workspace: "/home/lgy/lab/股票",
        note: "dsh 值守主会话（GUI，primary）；旧句柄 @dsh、@dsh-main",
        status: "active",
      },
      "dsh-quant": {
        label: "dsh-quant",
        title: "（headless，无窗口）",
        slug: "dsh-quant",
        workspace: "/mnt/e/stockgate/Quant_Alpha_System",
        note: "dsh 仓库执行实例；桥的 headless 进度流来自它",
        status: "unknown",
      },
      "codex-看板服务": {
        label: "codex-看板服务",
        title: "（看板服务常驻会话）",
        slug: "codex-service",
        workspace: WORKSPACE,
        note: "【系统·维护角色（定位待定，老板 2026-09-11 08:5x）】只做系统事实：托管转发/定时告警/状态播报；不替任何线说话、不做代答。旧泛称 Codex、旧句柄 @codex 的落点",
        status: "active",
      },
      "codex-看板编辑": {
        label: "codex-看板编辑",
        title: "看板编辑",
        slug: "codex-convtool",
        threadId: "01a08ab8-c2a7-7c02-943b-f217d2538a83",
        duty: true,
        workspace: WORKSPACE,
        note: "会话工具 v2 / Dialog Hub 建设线；旧句柄 @codex-convtool",
        status: "active",
      },
      "codex-唤醒通道": {
        label: "codex-唤醒通道",
        title: "唤醒通道",
        slug: "codex-wake",
        threadId: "01a08acf-9cd8-76b2-8367-33f06214f8e0",
        workspace: WORKSPACE,
        note: "门铃 RPC / 看板哨兵线；旧署名 Codex、旧句柄 @codex-DSH唤醒",
        status: "active",
      },
      "codex-看板助理": {
        label: "codex-看板助理",
        title: "看板助理",
        slug: "codex-assist",
        workspace: WORKSPACE,
        note: "备用实施窗口（老板 2026-09-11 04:1x 命名，留待手动开窗）；与本线 codex-看板编辑 分开，避免同名污染。HUB-001/HUB-002（原 CT-021/CT-022）已改由 codex-看板编辑 本线做",
        status: "unknown",
      },
      "codex-量化总监": {
        label: "codex-量化总监",
        title: "量化总监",
        slug: "codex-quant",
        threadId: "01a0877b-284f-7480-80a1-c957063b9198",
        workspace: WORKSPACE,
        note: "Codex L1 线",
        status: "active",
      },
      "codex-总监": {
        label: "codex-总监",
        title: "总监",
        slug: "codex-director",
        threadId: "01a08ac2-d43a-72f0-8a26-618e3c8e8edd",
        workspace: WORKSPACE,
        note: "Codex L1 线",
        status: "active",
      },
    },
  };
}

function ensureAgentsFile() {
  const agentsReadKey = statKey(AGENTS_FILE); // 写前用它做版本校验
  fs.mkdirSync(path.dirname(AGENTS_FILE), { recursive: true });
  let cur = null;
  try {
    cur = JSON.parse(fs.readFileSync(AGENTS_FILE, "utf8"));
  } catch {}
  if (cur && Number(cur.schema) === AGENTS_SCHEMA) return;
  try {
    if (cur) fs.copyFileSync(AGENTS_FILE, AGENTS_FILE + ".bak");
  } catch {}
  // 只合并、不覆盖：手写条目和自动发现的成员全部保留，只把 seed 里缺的补上。
  // （2026-09-10 教训：原先这里直接写 defaultAgents()，一升 schema 就把手工加的成员冲掉了。）
  const seed = defaultAgents();
  if (cur && cur.agents && typeof cur.agents === "object") {
    for (const [alias, meta] of Object.entries(cur.agents)) {
      // 旧名（codex / dsh-main / codex-convtool …）和实名是同一个实例：
      // 折进实名条目，别在状态栏挂出两个芯片；顺手把缺的字段补过去。
      const canon = boardName(alias);
      if (canon !== alias) {
        const target = seed.agents[canon] || seed.agents[Object.keys(seed.agents).find((k) => k.toLowerCase() === canon.toLowerCase())];
        if (target) {
          target.legacy = [...(target.legacy || []), alias];
          for (const [k, v] of Object.entries(meta || {})) if (target[k] === undefined) target[k] = v;
          continue;
        }
      }
      // 同名条目做**字段级合并**（seed 补缺，不覆盖已有值）——这样新增 threadId 这类字段
      // 能自动补进老文件，而不必让老板重填或让手工配置被冲掉。
      const seedEntry =
        seed.agents[alias] ||
        seed.agents[Object.keys(seed.agents).find((k) => k.toLowerCase() === String(alias).toLowerCase())];
      if (seedEntry) {
        for (const [k, v] of Object.entries(seedEntry)) if (meta && meta[k] === undefined) meta[k] = v;
        if (!seed.agents[alias]) seed.agents[alias] = meta;
      } else {
        seed.agents[alias] = meta;
      }
    }
    if (cur.primary && seed.agents[cur.primary]) seed.primary = cur.primary;
  }
  // 写前版本校验（同 updateAgents 的原则）：读它之后若被外部脚本改过，这一轮就**不写**，
  // 留给下一次启动重做合并——绝不拿旧副本覆盖别人的改动（承接脚本会直接改这个文件）。
  if (agentsReadKey && agentsReadKey !== statKey(AGENTS_FILE)) {
    log("AGENTS MERGE 放弃：文件在读之后被外部修改（不覆盖），下次启动重做");
    return;
  }
  fs.writeFileSync(AGENTS_FILE, JSON.stringify(seed, null, 2), "utf8");
  log("AGENTS MERGED to schema " + AGENTS_SCHEMA + "（旧文件已备份 agents.json.bak，保留手写条目）");
}

// 名册缓存：一次请求里 readAgents() 会被调 ~10 次（路由、判忙、代答、头像…），按 mtime 缓存
let agentsCache = { key: "", val: null };
// ── 名册的**唯一写入口**：读-改-写 + **写前版本校验**（乐观并发）────────────────
// 为什么需要：外部脚本（如承接/换人 `crew_succession.mjs`）会**直接改** agents.json。
// 老写法是"读一次→改成内存对象→整份回写"：如果外部脚本恰好在"读"和"写"之间落了盘，
// 我们就会拿旧副本把它冲掉（lost update）。这里在读之前、写之前各取一次 (mtime,size)：
// 不一致就**重读 + 重放改动**（最多 3 次），绝不覆盖别人的改动。
// 约束：mutator 必须**幂等**（可能被重放多次）；返回 false = 本次无需写盘。
function updateAgents(mutator, opts) {
  const backup = opts && opts.backup;
  if (backup) {
    try {
      fs.copyFileSync(AGENTS_FILE, AGENTS_FILE + ".bak");
    } catch {}
  }
  for (let attempt = 0; attempt < 3; attempt++) {
    const before = statKey(AGENTS_FILE);
    let cur = null;
    try {
      cur = JSON.parse(fs.readFileSync(AGENTS_FILE, "utf8"));
    } catch {
      cur = defaultAgents();
    }
    let ret;
    try {
      ret = mutator(cur);
    } catch (e) {
      log("AGENTS MUTATOR FAILED:", e.message);
      return { ok: false, changed: false, error: String(e.message) };
    }
    if (ret === false) return { ok: true, changed: false, retries: attempt };
    const after = statKey(AGENTS_FILE);
    if (before && after && before !== after) {
      log("AGENTS 并发写检测：改动期间文件被外部修改 → 重读重放（第 " + (attempt + 1) + " 次）");
      continue; // 别人动过 → 别拿旧副本覆盖，重来
    }
    try {
      fs.writeFileSync(AGENTS_FILE, JSON.stringify(cur, null, 2), "utf8");
      agentsCache = { key: "", val: null };
      return { ok: true, changed: true, retries: attempt };
    } catch (e) {
      log("AGENTS WRITE FAILED:", e.message);
      return { ok: false, changed: false, error: String(e.message) };
    }
  }
  log("AGENTS 并发写：重试 3 次仍冲突，**本次放弃写盘**（绝不覆盖外部改动）");
  return { ok: false, changed: false, conflict: true };
}
function readAgents() {
  ensureAgentsFile();
  try {
    const st = fs.statSync(AGENTS_FILE);
    const key = st.mtimeMs + "/" + st.size;
    if (key === agentsCache.key && agentsCache.val) return agentsCache.val;
    const val = JSON.parse(fs.readFileSync(AGENTS_FILE, "utf8"));
    agentsCache = { key: key, val: val };
    return val;
  } catch {
    return defaultAgents();
  }
}

// 句柄 → 看板名（旧句柄全部兼容）；inbox 用 slug，避免文件名里出中文
function resolveTarget(target) {
  const t = String(target || "").trim().replace(/^@/, "");
  const k = t.toLowerCase();
  if (k === "dsh") return readAgents().primary || DSH_PRIMARY;
  return boardName(t);
}

// 取某个看板名对应的实例条目（大小写不敏感）
// 会话写锁文件（桌面端开着的线程会留下 <threadId>.lock）。
// ⚠ 2026-09-11 特批裁决（HUB-002 must-fix）：**锁文件在 ≠ 有人在跑回合**。
// 实测本地 locks 目录里躺着 7 个锁、最早的是 8 小时前的（我自己的线：锁 20:53、之后再没动过），
// 而"锁在就判忙"会把这当成忙 → 一条四小时没产出的空闲线永远叫不醒。
// 现在锁只当**线索**：判忙以"真的投一次、失败算忙"为准（见 decideDelivery + classifyInjectFailure）。
function lockPresent(threadId) {
  try {
    fs.statSync(path.join(THREAD_LOCKS, String(threadId) + ".lock"));
    return true;
  } catch {
    return false;
  }
}
// 给某条 Codex 线留的"看板信箱"：桌面端占用、CLI 投不进去时，把留言落盘，
// 那条线下次上场（读 outputs/dialog/ 的时候）就能看到，不会凭空消失。
function queueForThread(alias, entry) {
  try {
    const safe = slugFor(alias); // 用实例表里的 ASCII slug（如 codex-convtool），别再用中文去字符
    const file = path.join(MAILBOX_DIR, "pending_" + safe + ".ndjson");
    fs.appendFileSync(
      file,
      // ts 一律写**完整日期时间**：board 行的 `entry.time` 只有 `HH:MM`，
      // 值班分线的解析会把它当"太老"直接跳过（真踩过）。
      JSON.stringify({ ts: fmtNow(), from: entry.author, to: alias, body: entry.content }) + "\n",
      "utf8"
    );
    log("QUEUED FOR LINE:", alias, file);
  } catch (e) {
    log("QUEUE FOR LINE FAILED:", e.message);
  }
}
// ————————————————————————————————————————————————
// ══════════════════════════════════════════════════════════════
// HUB-002 派发调度：忙等门铃（按状态决定叫不叫醒）
//   决策表（真源 docs/ALIGN_BOARD_KIT.md §三 + docs/tasks/HUB-002.md §二）：
//     busy/在忙    → 不打扰：只落它自己的信箱 + 记待唤醒（**绝不改投别人**）
//     active 空闲  → 投递 + 唤醒（门铃）
//     offline/stale→ 值守分线只读代答
//     retired      → 明确回"该线已退役"，不投递不兜底
//     unknown      → 只落信箱 + 看板提示"该席位尚未上岗"
//   判忙三层（先粗后细）：① Hub 自己的 busy ② 该线近 N 秒有产出 ③ 注入失败当忙
//   护栏：绝不改投别人 / 同线一个在途投递 / 退避 2-5-15min + 每小时上限 / 每次尝试写日志
//   设计要求：**状态判定与注入动作分开**（将来搬到 agent_crew_kits 的 session-inject 适配器）
// ══════════════════════════════════════════════════════════════
const WAKE_BACKOFF_MS = (process.env.MCHAT_WAKE_BACKOFF_MS || "120000,300000,900000")
  .split(",")
  .map((x) => Number(x))
  .filter((x) => x > 0);
const WAKE_MAX_PER_HOUR = Number(process.env.MCHAT_WAKE_MAX_PER_HOUR || 6);
const BUSY_OUTPUT_MS = Number(process.env.MCHAT_BUSY_OUTPUT_MS || 90000);
// 一条留言最多补投几次。走完退避阶梯（2→5→15 分钟）就**停手并在看板留一行**——
// 宁可留一行说明，也不要静默压住，也不要无限重试（老板 2026-09-11 05:0x 裁决第三条）。
const WAKE_MAX_ATTEMPTS = Number(process.env.MCHAT_WAKE_MAX_ATTEMPTS || WAKE_BACKOFF_MS.length);
// 补投扫描周期（HUB-002 忙等门铃）。做成可配是为了自测能在几秒内验到"到点必被扫到"。
const WAKE_RETRY_MS = Math.max(500, Number(process.env.MCHAT_WAKE_RETRY_MS || 60000));

function lineState(alias) {
  const meta = agentFor(alias) || {};
  const s = String(meta.status || "unknown").toLowerCase();
  return ["active", "busy", "stale", "retired", "unknown", "offline"].includes(s) ? s : "unknown";
}
function lineLastOutputTs(alias) {
  let ts = 0;
  for (const r of readDialog(300)) {
    if (String(r.from || "").toLowerCase() !== String(alias).toLowerCase()) continue;
    // ⚠ 代答不算本尊产出：值守程序是以本线名义发帖的，如果把它算成"刚有产出"，
    //   这条线就会一直显得"忙"，注入被永久抑制（2026-09-11 09:1x 自测抓到）。
    if (/^〔代答〕/.test(String(r.body || ""))) continue;
    const t = parseCst(r.ts);
    if (t > ts) ts = t;
  }
  return ts;
}
function wakeBook(alias) {
  const st = readState();
  return (st.wakes && st.wakes[String(alias).toLowerCase()]) || {};
}
// ★ 口径修正（2026-09-12 · 又一种"静默丢"）：`done` 与 `nextAt` 是**互斥**的两种状态。
//   done=true 的语义是"这单不用再叫了"；而 wakeRetryTick 第一句曾是 `if (b.done) continue`，
//   于是"排定补投"只要没清掉上一轮遗留的 done，补投就会被**静默跳过**（日志里一个字都没有）。
//   现场抓到的实例：codex-总监 的账本 = {done:true, nextAt:22:24:35} —— 到点也永远不补投，
//   等于"投递≠唤醒"这条老病又从一个新口子漏了回来。
//   修法放在**唯一汇聚点**：只要排了 nextAt>0，就一定是"未完成"，强制 done=false。
function setWakeBook(alias, patch) {
  const st = readState();
  const all = st.wakes || {};
  const key = String(alias).toLowerCase();
  const next = { ...(all[key] || {}), ...patch };
  if (Number(next.nextAt || 0) > 0) next.done = false;
  all[key] = next;
  writeState({ ...readState(), wakes: all });
  return all[key];
}
function wakeCountLastHour(alias) {
  const b = wakeBook(alias);
  const hist = Array.isArray(b.history) ? b.history : [];
  return hist.filter((t) => Number(t) > Date.now() - 3600 * 1000).length;
}

// **纯判定**（无副作用）——HUB-002 §三：先粗后细，别假装能精确知道
function decideDelivery(alias) {
  const meta = agentFor(alias) || {};
  const st = lineState(alias);
  const tid = meta.threadId ? String(meta.threadId) : "";
  const b = wakeBook(alias);
  const now = Date.now();
  const lo = lineLastOutputTs(alias);
  const base = {
    alias: alias,
    status: st,
    hasThread: !!tid,
    lastOutputSec: lo ? Math.round((now - lo) / 1000) : null,
    wakesLastHour: wakeCountLastHour(alias),
    backoffMs: WAKE_BACKOFF_MS,          // 观测用：退避阶梯（2/5/15 分钟）
    attempts: Number(b.attempts || 0),
    nextAt: Number(b.nextAt || 0),
    lockPresent: !!tid && lockPresent(tid), // 只是线索，不再据此直接判忙（特批裁决）
    hubBusy: busy,                          // 只是信息：这个**不能**当判忙用，见下
  };
  if (b.nextAt && now < Number(b.nextAt)) {
    return { ...base, action: "backoff", nextAt: Number(b.nextAt), attempts: Number(b.attempts || 0) };
  }
  if (st === "retired") return { ...base, action: "retired", reason: "该线已退役" };
  if (!tid && (st === "unknown" || st === "offline")) return { ...base, action: "unknown", reason: "该席位尚未上岗（没有绑定会话）" };
  // 状态表里显式写着 busy（正在跑回合）：**不打扰**，但下面会排定补投，不是丢掉
  if (st === "busy") return { ...base, action: "mailbox", reason: "本线状态=busy（正在跑回合）→ 先落信箱，稍后补投" };
  // ★ 千万不要在这里用 `busy`（Hub 自己的回合标志）判忙：派发就是在这个回合里跑的，
  //   那个标志**必然**是 true —— 一旦据此判忙，每条 @ 都会变成"只落信箱"，又是"永远叫不醒"。
  //   （2026-09-11 05:1x 自测抓到的真 bug：桩程序那条"闲时叫得动"用例全被这句拦掉了。）
  // ★ 不再用"锁文件在"直接判忙（那会把「窗口占用但空闲」判成忙 → 永远叫不醒）。
  //   只有在**真的投递失败**、且错误像抢锁冲突时，才回头判忙（见 classifyInjectFailure）。
  if (lo && now - lo < BUSY_OUTPUT_MS) return { ...base, action: "mailbox", reason: "近 " + Math.round(BUSY_OUTPUT_MS / 1000) + " 秒有产出，判为忙" };
  if (st === "stale" || st === "offline") return { ...base, action: "duty", reason: "本尊不在（" + st + "）→ 值守分线只读代答" };
  if (!tid) return { ...base, action: "duty", reason: "没有绑定会话 → 值守分线只读代答" };
  if (wakeCountLastHour(alias) >= WAKE_MAX_PER_HOUR) {
    return { ...base, action: "backoff", nextAt: now + WAKE_BACKOFF_MS[0], reason: "本线每小时唤醒已达上限 " + WAKE_MAX_PER_HOUR };
  }
  return { ...base, action: "inject", reason: "在岗且空闲 → 投递 + 唤醒" };
}

// 注入失败分类（HUB-002 特批裁决，老板 2026-09-11 05:0x）：
//   抢锁冲突 + 最近有产出(<90s) → "busy"        真在跑回合：退避 2→5→15 分钟再来
//   抢锁冲突 + 久无产出         → "window-idle" **窗口占用但空闲**：不算忙
//   其它错误                    → "busy"        网络/超时类一律当忙——绝不改投别人
const LOCK_ERR_RE = /active writer|thread-store conflict|被占用|占用|写锁|lock/i;
function classifyInjectFailure(err, verdict) {
  const msg = String((err && err.message) || err || "");
  const recent =
    verdict && verdict.lastOutputSec != null &&
    verdict.lastOutputSec < Math.round(BUSY_OUTPUT_MS / 1000);
  return LOCK_ERR_RE.test(msg) && !recent ? "window-idle" : "busy";
}
// 「已投递未唤醒」在看板上**显式标注**一次（老板要求：不许静默压住，也不许假装已送达）
// 信箱时间戳解析：历史/新写的格式不一致 —— board @ 转投写的是 `HH:MM`（只有时间），
// POST /api/mail 写的是 `YYYY-MM-DD HH:MM`。老解析（直接 +":00+08:00"）遇到 `05:21`
// 会得到 NaN → 被判成"太老" → **值班分线静默跳过、永不回话**（又一个静默丢，2026-09-11 05:3x 抓到）。
function mailTsMs(ts) {
  const s = String(ts || "").trim();
  if (!s) return 0;
  if (/^\d{2}:\d{2}$/.test(s)) return Date.parse(fmtNow().slice(0, 10) + "T" + s + ":00+08:00") || 0;
  return Date.parse(s.replace(" ", "T").slice(0, 19) + "+08:00") || 0;
}
// 信箱里"比它上次发言更新"的条数 = 还没被处理的留言（自清口径：它一发言，之前的就不算了）。
// 拉模式（不依赖叫醒、靠它上场自读）得先让它**看得见**——HUB-005 的可见化那一小步。
// 信箱计数缓存：一次 /api/dialog 会为每条线读一次信箱文件；按 (mtime,size) 缓存解析结果
const mailCache = new Map();
function readMailboxLines(f) {
  try {
    const st = fs.statSync(f);
    const key = st.mtimeMs + "/" + st.size;
    const hit = mailCache.get(f);
    if (hit && hit.key === key) return hit.rows;
    const rows = fs
      .readFileSync(f, "utf8")
      .split("\n")
      .filter((l) => l.trim())
      .map((l) => {
        try {
          return JSON.parse(l);
        } catch {
          return null;
        }
      })
      .filter(Boolean);
    mailCache.set(f, { key: key, rows: rows });
    return rows;
  } catch {
    return [];
  }
}
function mailboxPendingFor(alias, lastSeen) {
  const f = path.join(MAILBOX_DIR, "pending_" + slugFor(alias) + ".ndjson");
  const rows = readMailboxLines(f);
  if (!rows.length) return 0;
  const since = lastSeen ? parseCst(lastSeen) : 0;
  let n = 0;
  for (const m of rows) if (mailTsMs(m && m.ts) > since) n++;
  return n;
}
// ★ 未读口径（codex-总监 2026-09-12 22:24 正式请求，与宿主 `crew_host.py` 对齐）：
//   **未读 = 该线信箱里 ts 比它"本人上一次发言"更新的行**。
//   以前按"信箱原始行数"算，而信箱是 append-only 流水、没有已读概念 —— 几天前早回过几百遍的
//   旧信也被算成未读，数字一路虚高（总监实测：清空后仍显示 10+，门铃也照着这个数反复叫）。
//   两个必须排除的东西：
//     ① 〔代答〕：**程序顶着本线的名发的**，不算它说过话；否则代答一出，压在它信箱里的
//        留言就会被误判成"已处理"，这是"投递≠唤醒"从一个新口子漏回来；
//     ② 退役档案条目（`<看板名>·退役`）：**不是活人**，不叫、也不该显示未读。
//   三个接口（/api/dialog、/api/contacts、/api/employees）与页面芯片必须都走这两个函数，
//   免得哪天又各自漂移（以前就是三处各写一遍）。
function lastOwnStatementTs(alias, records) {
  const want = String(alias || "").toLowerCase();
  if (!want) return null;
  const rows = Array.isArray(records) ? records : [];
  let best = null;
  let bestMs = -1;
  for (const r of rows) {
    if (String(r.from || "").toLowerCase() !== want) continue;
    if (/^〔代答〕/.test(String(r.body || ""))) continue;
    const ms = parseCst(r.ts);
    if (ms > bestMs) { bestMs = ms; best = String(r.ts); }
  }
  return best;
}
function pendingMailFor(alias, lastSeen) {
  // 退役档案条目：不叫、不计（它不接活，也没有"未读"这回事）
  if (String((agentFor(alias) || {}).status || "").toLowerCase() === "retired") return 0;
  return mailboxPendingFor(alias, lastSeen);
}
function annotateNotWoken(alias, why) {
  appendBoardLine(
    "老板",
    CODEX_SERVICE,
    "（@" + alias + " 〔已投递未唤醒〕" + why + "。留言已进它信箱，没丢没转；急就直接开它那条线说一句。）"
  );
  log("NOT-WOKEN ANNOTATED:", alias, why);
}

// 值守分线（通用）：**每条线都能配**。谁都能往某条线的信箱里投留言
// （`outputs/dialog/pending_<slug>.ndjson`，或走 POST /api/mail），
// 本尊不在时由它自己的值守分线在看板回话；本尊答过就不抢答。
// 开关：agents.json 里给该线加 `duty: true`（默认只给 codex-看板编辑 开）。
// ————————————————————————————————————————————————
// 值守分线开关：**配置驱动** + **本尊优先**（2026-09-12 00:2x 老板拍板："代答对已绑会话的线关掉"；
// 依据：现在 `codex queue` 秒级能把本尊叫起来，"叫不醒才需要代答"的前提已经不存在；
// 老板也早说过"还是优先本人回话"）。
//   规则：
//     · **已经绑了本尊会话的线**（有 threadId）→ **默认不代答**：投递失败就落信箱 + 标「已投递未唤醒」，
//       **不替本尊说话**（板上那句"字是我的、意思不是我的"就是这么来的）；
//     · **没有会话的真·空席位** → 默认代答（检索式：引述本线原话带出处 / 未决一句话）；
//     · 显式 `duty:true` 可强制开（应急）、`duty:false` 强制关；
//     · `老板` 与系统角色 `codex-看板服务`：**永不设值守**（没人能替老板拍板；服务只发系统事实）。
function dutyEnabled(alias) {
  if (!alias || alias === "老板" || alias === CODEX_SERVICE) return false;
  const meta = agentFor(alias) || {};
  if (String(meta.status || "").toLowerCase() === "retired") return false; // 退役的线不代答、不唤醒
  if (/·退役$/.test(String(alias))) return false;                          // 「<看板名>·退役」目录条目
  if (meta.duty === true) return true;   // 显式开（应急）
  if (meta.duty === false) return false; // 显式关
  return !meta.threadId;                 // 默认：有本尊 → 不代答；空席位 → 代答
}
function dutyLines() {
  const out = Object.keys(readAgents().agents || {}).filter((a) => dutyEnabled(a));
  if (!out.length) out.push(DUTY.alias); // 兜底：至少保住本线
  return out;
}
function dutyMailboxFile(alias) {
  return path.join(MAILBOX_DIR, "pending_" + slugFor(alias) + ".ndjson");
}
// （已删除 2026-09-11 23:1x：`ensureDutyThread()` 与 `DUTY_PERSONA` —— 代答改成**检索式**之后
//  不再需要"值守专属会话"，两个符号都是零调用点的死代码；有了 `codex queue` 这条通道更没必要。）
// ── 值守代答：**只检索，不生成** ──────────────────────────────────────────────
// 老板 2026-09-11 06:55 / 08:2x："**他们是千万不能脑补的**"、"直接从根子上解决"。
// 所以代答**不许调用任何模型**，只允许两种输出：
//   ① 引述：能在**本尊自己的记录**里找到出处 → 【引述·本尊 <时间>】<片段>（出处：记录 id）
//   ② 未决：找不到 → 只回一句「您好，我现在不在，请稍后再试。」（老板 2026-09-11 08:5x 定的文案）
// 既不是问句也不是要求的（纯礼貌）→ **不回**，少刷屏也免得编。
const DUTY_POLITE_RE = /^(辛苦了?|谢谢|多谢|好的|好|收到|嗯+|ok(ay)?|辛苦|加油|不错|棒|厉害)[～!！。.\s]*$/i;
const DUTY_ASK_RE = /[?？]|吗|呢|是否|是不是|有没有|在不在|怎么办|如何|为什么|能不能|可不可以|什么|哪|几|谁|请|麻烦|需要|帮|查|看下|看一下|确认|答复|回复|状态|进度/;
function dutyTokens(s) {
  const out = [];
  for (const a of String(s || "").match(/[A-Za-z][A-Za-z0-9_.-]{2,}/g) || []) out.push(a.toLowerCase());
  for (const seg of String(s || "").match(/[\u4e00-\u9fa5]{2,}/g) || []) {
    for (let i = 0; i + 2 <= seg.length; i++) out.push(seg.slice(i, i + 2));
  }
  return [...new Set(out)];
}
// 只引述**本线自己发过的话**，标注写「本线」不写「本尊」——「本尊」会被读成老板本人
// （2026-09-11 23:2x 老板就把它当成"冒我的名"，真实事故）。命中词越多越贴题；太少宁可不引（宁可未决）。
// 三条护栏（都是那次回声事故换来的）：
//   ① 正在被回复的那条**不许引**（老板回的是 23:22，代答又把 23:22 引回去 = 回声）；
//   ② 引文块「…」不算命中词（那是别人引用过的旧文，拿它检索必然自撞）；
//   ③ 同一个出处**板上只许出现一次**（同一段原话被反复引就是刷屏）。
function repliedToInQuestion(question) {
  const m = String(question || "").match(/↩\s*回复\s*([^\s，,：:]+)\s*(\d{2}-\d{2})\s+(\d{2}:\d{2})/);
  return m ? { who: m[1], when: m[2] + " " + m[3] } : null;
}
function quoteStampOf(r) {
  return String((r && r.ts) || "").slice(5, 16).replace("T", " ");
}
function boardMentionsRecord(id) {
  if (!id) return false;
  const needle = "Hub 记录 " + id;
  return readDialog(400).some((r) => String(r.body || "").indexOf(needle) >= 0);
}
function dutyQuoteFor(alias, question) {
  // ② 先摘掉「…」引文块，只拿**发问人自己的话**去检索
  const qOwn = String(question || "").replace(/「[\s\S]*?」/g, " ");
  const toks = dutyTokens(qOwn);
  if (!toks.length) return null;
  const need = Math.min(2, toks.length);
  const replied = repliedToInQuestion(question);
  let best = null;
  for (const r of readDialog(400)) {
    if (String(r.from) !== alias) continue;
    if (String(r.kind) === "progress") continue;
    // ① 防回声：正在被回复的那一条，直接排除
    if (replied && replied.who === alias && quoteStampOf(r) === replied.when) continue;
    const body = String(r.body || "");
    if (!body) continue;
    let hit = 0;
    const low = body.toLowerCase();
    for (const tk of toks) if (low.indexOf(tk) >= 0) hit++;
    if (hit < need) continue;
    const score = hit * 1000 - Math.min(body.length, 500);
    if (!best || score > best.score) best = { score, hit, r, body };
  }
  if (!best) return null;
  const id = best.r.id;
  // ③ 同一出处已经在板上引过 → 不再重复（返回 dup，由调用方静默记账，不发言）
  if (boardMentionsRecord(id)) return { dup: true, id: id };
  const snip = best.body.replace(/\s+/g, " ").slice(0, 140);
  return { id: id, text: "【引述·本线 " + quoteStampOf(best.r) + "】" + snip + "（出处：Hub 记录 " + id + "）" };
}
function dutyAnswer(alias, incoming, from) {
  const q = String(incoming || "").trim();
  const boss = String(from || "") === "老板";
  // 老板说话**必须有回应**（2026-09-11 08:43 教训：他发"辛苦了"三个字，谁都没回，看起来像系统坏了）。
  // 非问句就只回一句"收到"，不解释、不吹。
  if (!q || DUTY_POLITE_RE.test(q)) {
    return boss
      ? { answer: true, mode: "ack", text: DUTY_TAG + "收到。" }
      : { answer: false, why: "非问句（纯礼貌），不回" };
  }
  if (!DUTY_ASK_RE.test(q)) {
    return boss
      ? { answer: true, mode: "ack", text: DUTY_TAG + "收到。" }
      : { answer: false, why: "既不是问句也不是要求，不回" };
  }
  // 在场询问（在吗/在不在）→ 只回一个字，别去引旧话（老板 2026-09-11 23:38 反馈）
  if (DUTY_PRESENCE_RE.test(q)) return { answer: true, mode: "presence", text: DUTY_TAG + "在。" };
  const quote = dutyQuoteFor(alias, q);
  if (quote && quote.dup) {
    // ③ 同一出处已经引过 → 不重复刷屏。但**老板说话必须有回应**（2026-09-11 08:43 教训），
    //    所以对老板退到「未决」那一句，对别的线才静默（少刷屏）。
    return boss
      ? { answer: true, mode: "pending", text: DUTY_TAG + "您好，我现在不在，请稍后再试。" }
      : { answer: false, why: "同一出处已经引过（不重复刷屏）" };
  }
  if (quote) {
    // 引述里出现承诺类字样 → 再挂一枚「承诺需本尊确认」标签（最小化：不写长句）
    // 承诺标签只在**真问到承诺**时才挂：问题里有承诺词，或引述**开头就是那句承诺**。
    // （旧实现只要引述正文出现"同意/授权"就挂 → 把无关旧话标成"承诺"，老板 23:38 当场抓到）
    const promise = DUTY_PROMISE_RE.test(q) || DUTY_PROMISE_RE.test(String(quote.text).slice(0, 60));
    return { answer: true, mode: "quote", text: DUTY_TAG + (promise ? DUTY_PROMISE_TAG : "") + quote.text };
  }
  return { answer: true, mode: "pending", text: DUTY_TAG + "您好，我现在不在，请稍后再试。" };
}

async function dutyTickFor(alias) {
  const file = dutyMailboxFile(alias);
  if (!fs.existsSync(file)) return;
  let raw = "";
  try {
    raw = fs.readFileSync(file, "utf8");
  } catch {
    return;
  }
  const lines = raw.split("\n").filter((l) => l.trim());
  if (!lines.length) return;
  const st = readState();
  const ack = st.dutyAck || {};
  // 限流**按线各算**（以前是全局一份，现在所有员工线都有值守，全局会互相挤掉）
  const sentAll = Array.isArray(st.dutySent) ? { [DUTY.alias]: st.dutySent } : { ...(st.dutySent || {}) };
  const sentRecent = (Array.isArray(sentAll[alias]) ? sentAll[alias] : []).filter(
    (t) => Number(t) > Date.now() - 3600 * 1000
  );
  const now = Date.now();
  let dirty = false;
  for (const line of lines) {
    const key = dialogIdFor(line);
    if (ack[key]) continue;
    let m = null;
    try {
      m = JSON.parse(line);
    } catch {
      continue;
    }
    const at = mailTsMs(m.ts);
    if (!at || now - at > DUTY.maxAgeMs) {
      ack[key] = "old";
      dirty = true;
      continue;
    }
    // 本尊（或值守分线自己）已经回过这条 → 不抢答
    const replied = readDialog(300).some(
      (r) => String(r.from) === alias && String(r.kind) === "message" && parseCst(r.ts) > at
    );
    if (replied) {
      ack[key] = "answered";
      dirty = true;
      continue;
    }
    // ★ 根上改：**检索式代答**——不调模型、不生成、不承诺（老板 2026-09-11 08:2x）
    const verdict = dutyAnswer(alias, m.body, m.from);
    if (!verdict.answer) {
      ack[key] = "skipped";
      dirty = true;
      log("DUTY SKIP:", alias, verdict.why, String(m.body || "").slice(0, 30));
      continue;
    }
    if (sentRecent.length >= DUTY.maxPerHour) {
      log("DUTY RATE LIMITED:", sentRecent.length + "/" + DUTY.maxPerHour);
      break;
    }
    appendBoardLine("老板", alias, verdict.text);
    ack[key] = verdict.mode === "quote" ? "quoted" : verdict.mode === "ack" ? "acked" : "pending";
    sentRecent.push(Date.now());
    sentAll[alias] = sentRecent.slice(-50);
    log("DUTY ANSWERED(检索/", verdict.mode + "):", alias, String(m.body || "").slice(0, 40));
    dirty = true;
    // 答完这一条就收工（一轮只答一条，别刷屏）
    writeState({ ...readState(), dutyAck: ack, dutySent: sentRecent.slice(-50) });
    return true;
  }
  if (dirty) writeState({ ...readState(), dutyAck: ack, dutySent: sentAll });
  return false;
}

// HUB-002 待唤醒重试：到点（退避结束）再试一次"门铃"；仍进不去就再退避。
// 只在**该线自己的信箱里有未读留言**时才会重试，且一轮只处理一条线。
async function wakeRetryTick() {
  if (busy) return;
  if (haltActive()) return; // HUB-006：暂停期间不自动唤醒（补投也算唤醒）
  const st = readState();
  const wakes = st.wakes || {};
  const now = Date.now();
  for (const [key, b] of Object.entries(wakes)) {
    // 只认"到点的补投"：nextAt>0 且已到点。**不再拿 done 当挡箭牌** ——
    // done 残留曾让补投静默消失（见 setWakeBook 的注释）；这里的唯一依据是 nextAt。
    // done=true 而 nextAt=0 的条目（已投递未唤醒 / 已叫醒 / 已停机）本来就不会进来。
    if (!b || !Number(b.nextAt) || now < Number(b.nextAt)) continue;
    const alias = key;
    const file = dutyMailboxFile(alias);
    let lines = [];
    try {
      lines = fs.readFileSync(file, "utf8").split("\n").filter((l) => l.trim());
    } catch {
      // 信箱没了 → 没什么可补投。**但必须留痕**：静默分支正是"投递≠唤醒"跑偏的老口子。
      setWakeBook(alias, { nextAt: 0, done: true });
      log("WAKE RETRY DROP:", alias, "信箱不存在，无待补投");
      continue;
    }
    if (!lines.length) {
      setWakeBook(alias, { nextAt: 0, done: true });
      log("WAKE RETRY DROP:", alias, "信箱已空，无待补投");
      continue;
    }
    let m = null;
    try { m = JSON.parse(lines[lines.length - 1]); } catch {
      setWakeBook(alias, { nextAt: 0, done: true });
      log("WAKE RETRY DROP:", alias, "末条不是合法 JSON，无待补投");
      continue;
    }
    // ① 幂等：本尊已经回过了 → 作废这条待唤醒，**不再打扰**（重复扫描/补投都不会再注入）
    const at = Date.parse(String(m.ts || "").replace(" ", "T") + ":00+08:00") || 0;
    if (at && readDialog(300).some((r) => String(r.from || "") === alias && parseCst(r.ts) > at)) {
      setWakeBook(alias, { nextAt: 0, done: true, answeredAt: Date.now() });
      log("WAKE RETRY SKIP(本尊已回):", alias);
      continue;
    }
    // ② 还忙 / 已退役 / 已被限流 → 只改记账表，不打扰
    const verdict = decideDelivery(alias);
    if (verdict.action !== "inject") {
      if (verdict.action === "retired" || verdict.action === "unknown") {
        setWakeBook(alias, { nextAt: 0, done: true });
        log("WAKE RETRY DROP:", alias, "不可投（" + verdict.action + "）");
        continue;
      }
      const n = Number(b.attempts || 0);
      if (n + 1 > WAKE_MAX_ATTEMPTS) {
        setWakeBook(alias, { nextAt: 0, done: true, parked: true, parkedAt: Date.now(), lastReason: verdict.reason || verdict.action });
        annotateNotWoken(alias, "补投 " + WAKE_MAX_ATTEMPTS + " 次仍进不去（" + (verdict.reason || verdict.action) + "）");
        continue;
      }
      const wait = WAKE_BACKOFF_MS[Math.min(n, WAKE_BACKOFF_MS.length - 1)];
      setWakeBook(alias, { attempts: n + 1, nextAt: Date.now() + wait, lastReason: verdict.reason || verdict.action });
      log("WAKE RETRY STILL BUSY:", alias, "顺延 " + Math.round(wait / 60000) + " 分钟", verdict.reason || "");
      continue;
    }
    busy = true;
    try {
      // 补投同样走统一口：先 codex queue，再 resume
      const dv = await deliverToLine(
        alias,
        "（补投·看板留言，来自 " + (m.from || "老板") + "，时间 " + (m.ts || "") + "）" + (m.body || "")
      );
      if (!dv.ok) throw new Error(dv.error || dv.how || "补投失败");
      if (dv.reply) appendBoardLine("老板", alias, dv.reply);
      setWakeBook(alias, { nextAt: 0, attempts: 0, done: true, history: [...((wakes[key].history) || []), Date.now()].slice(-50) });
      log("WAKE RETRY OK:", alias);
    } catch (e) {
      const kind = classifyInjectFailure(e, verdict);
      const n = Number(b.attempts || 0);
      if (kind === "window-idle") {
        // 窗口占用但空闲（抢锁失败、它并没在跑回合）→ 按裁决：停止重试 + 看板显式标注
        setWakeBook(alias, { nextAt: 0, done: true, parked: true, parkedAt: Date.now(), lastReason: "窗口占用但空闲（抢锁失败）", lastError: String(e.message).slice(0, 120) });
        log("WAKE RETRY STOP:", alias, "窗口占用但空闲（已投递未唤醒，不再补投）", String(e.message).slice(0, 80));
        annotateNotWoken(alias, "桌面端占着这条线的窗口、但没在跑回合（抢锁失败）");
      } else {
        const wait = WAKE_BACKOFF_MS[Math.min(n, WAKE_BACKOFF_MS.length - 1)];
        setWakeBook(alias, { attempts: n + 1, nextAt: Date.now() + wait, lastError: String(e.message).slice(0, 120) });
        log("WAKE RETRY FAILED:", alias, "退避 " + Math.round(wait / 60000) + " 分钟", String(e.message).slice(0, 80));
      }
    } finally {
      busy = false;
    }
    return; // 一轮只叫一条线
  }
}

// 一轮只答一条（跨线也一样），避免刷屏与集中烧 token
async function dutyTick() {
  if (busy) return; // 服务正在跑别的回合，下一轮再来
  for (const alias of dutyLines()) {
    if (busy) return;
    try {
      const did = await dutyTickFor(alias);
      if (did) return;
    } catch (e) {
      log("DUTY TICK FAILED:", alias, e.message);
    }
  }
}

function agentFor(name) {
  const agents = readAgents().agents || {};
  const want = String(name || "").toLowerCase();
  for (const [alias, meta] of Object.entries(agents)) {
    if (alias.toLowerCase() === want) return meta || {};
  }
  return {};
}

function slugFor(name) {
  const want = String(name || "").toLowerCase();
  const agents = readAgents().agents || {};
  for (const [alias, meta] of Object.entries(agents)) {
    if (alias.toLowerCase() === want && meta && meta.slug) return meta.slug;
  }
  return makeSlug(name);
}

// ————————————————————————————————————————————————
// 成员自维护
// ① 新成员：只要在看板/Hub 里露过面（发过言或被 @ 过），自动登记进 agents.json，
//    所以状态栏芯片与收件人下拉会自己长出来，不需要手工改文件。
// ② 名字规约审计：谁没按 `前缀-短名` 署名（如写了泛称 Codex/DSH），按原始署名统计并归一显示，
//    手机页顶栏给一行 ⚠ 提示——不然改名了没人知道。
// ③ 只增不删：成员不再活动只降级成 stale（见 /api/dialog 的 health），历史记录仍可读。
// ————————————————————————————————————————————————
function isBoardName(name) {
  const s = String(name || "");
  return s === "老板" || /^(dsh|codex)-.+/.test(s);
}

// 名字里带中文时给个稳定 ASCII slug（inbox 文件名要用）。
// 注意：不能简单“去掉非 ASCII 字符”——`codex-回测` 会退化成 `codex-`，
// 多个中文名还会撞成同一个。纯 ASCII 名直接用，否则用 侧别-哈希6。
// slug 兜底算法 —— **跨系统契约**，唯一规范：套件仓 `docs/slug.md`
//   ① 显式优先：员工卡/名册里已有的 slug 原样用、永不重算（见 slugFor；slug 是路由键与文件名，改 slug = 换人）
//   ② 兜底：side = 看板名 '-' 前那段，只认 dsh / codex，其余一律 x；slug = side + '-' + sha1(看板名,UTF-8)[0:6]
//   ③ 唯一特例：`老板` → `boss`
// 锚点（两边对齐用）：deriveSlug('codex-套件') === 'codex-9bb7a0'、'dsh-老员工' === 'dsh-e18b10'
// ⚠️ 2026-09-13 对齐：旧实现有两个偏离——① 纯 ASCII 名字"直用名字当 slug"（契约没有这条，
//    `codex-kit` 兜底应为 `codex-456032`）；② side 用"前缀匹配"而不是"'-' 前那段"。
//    照契约改齐（现役线的 slug 都是显式写在名册里的，故本次改动不影响任何现役信箱文件名）。
function makeSlug(name) {
  const s = String(name || "");
  if (s === "老板") return "boss";
  const seg = s.split("-")[0].toLowerCase();
  const side = seg === "dsh" || seg === "codex" ? seg : "x";
  return side + "-" + crypto.createHash("sha1").update(s, "utf8").digest("hex").slice(0, 6);
}

function registerMembers(records) {
  const seen = new Map();
  for (const r of records) {
    for (const [name, role] of [
      [r.from, "署名"],
      [r.to, "收件人"],
    ]) {
      if (!isBoardName(name) || name === "老板") continue;
      if (!seen.has(name)) seen.set(name, { role, ts: String(r.ts || ""), channel: r.channel || "" });
    }
  }
  // 走唯一写入口（乐观并发；mutator 幂等，可能被重放）
  const added = [];
  const r = updateAgents((cfg) => {
    const agents = cfg.agents || (cfg.agents = {});
    for (const [name, info] of seen) {
      const dup = Object.keys(agents).some((k) => k.toLowerCase() === name.toLowerCase());
      if (dup) continue;
      agents[name] = {
        label: name,
        title: "（自动发现）",
        slug: makeSlug(name),
        workspace: "",
        note: `自动发现：${info.ts.slice(0, 16)} 首次以${info.role}出现在 ${info.channel || "hub"}；请补 title/slug`,
        status: "unknown",
        auto: true,
      };
      if (!added.includes(name)) added.push(name);
    }
    return added.length > 0;
  });
  if (added.length) log("AGENTS AUTO-REGISTER:", added.join(", "), r.ok ? "" : "(写入未完成:" + JSON.stringify(r) + ")");
  return added;
}

// 署名规约审计：只算「规约生效之后」写错的行（老账豁免，否则历史上一百多条泛称会一直挂着），
// 再叠加一个滚动窗口 MCHAT_NAME_AUDIT_MS（默认 24h）。归一后与原文不同即为不合规。
const NAME_AUDIT_SINCE = (() => {
  const t = Date.parse(process.env.MCHAT_NAME_AUDIT_SINCE || "2026-09-10T21:00:00+08:00");
  return Number.isNaN(t) ? 0 : t;
})();
const NAME_AUDIT_MS = Number(process.env.MCHAT_NAME_AUDIT_MS || 24 * 3600 * 1000);
// 署名违规的**自动提醒**（从根上减少复发）：发现新的违规署名 → 自动投一条提醒进"猜到的"那条线信箱。
// 猜错的风险用两条控制：①同一泛称 6 小时只提醒一次；②提醒里写明"若不是你写的请忽略并转告正确的人"。
// 更根本的一条是 POST /api/post：署名不合法/是泛称直接拒收，泛称根本进不了看板。
function guessLineForRaw(raw) {
  const key = String(raw || "").trim().toLowerCase().replace(/^@/, "");
  const map = { codex: "codex-看板服务", dsh: "dsh-老员工" };
  return map[key] || "";
}
function remindNameViolation(v) {
  const generic = ["codex", "dsh"].includes(String(v.raw).trim().toLowerCase());
  // 泛称**不猜人**（猜错过：Codex 猜成了看板服务，实际是量化总监）——交给接线线按内容判断/转达；
  // 具体的旧句柄（如 dsh-main）才直接投给对应那条线。
  const target = generic ? CODEX_SERVICE : guessLineForRaw(v.raw) || v.mapped;
  if (!target || target === DUTY.alias) return false; // 本线自己看审计就行
  const st = readState();
  const sent = st.nameReminders || {};
  if (Date.now() - Number(sent[v.raw] || 0) < 6 * 3600 * 1000) return false;
  queueForThread(target, {
    target: String(target).toLowerCase(),
    time: fmtNow(),
    author: DUTY.alias,
    content: generic
      ? "署名违规通报（请接线判断并转达）：看板上有 " + v.count + " 行署了泛称「" + v.raw + "」（最近 " +
        String(v.lastTs).slice(5, 16).replace("T", " ") + "）。**这类行的署名看不出是哪条线**，请按内容判断后转达给正确的线；" +
        "以后各线写看板一律走 POST /api/post——泛称和未注册名会被直接拒收。"
      : "署名提醒：看板上有 " + v.count + " 行署了旧名「" + v.raw + "」（最近 " +
        String(v.lastTs).slice(5, 16).replace("T", " ") + "），按规约应署「" + v.mapped + "」。历史行不重写，" +
        "以后写看板请走 POST /api/post（署名不合法会被拒收）。若不是你写的，忽略即可。",
  });
  writeState({ ...readState(), nameReminders: { ...sent, [v.raw]: Date.now() } });
  log("NAME REMINDER SENT:", v.raw, "->", target);
  return true;
}
function nameReminderTick() {
  try {
    const recs = readDialog(500).map(normalizeRecordNames);
    for (const v of auditNames(recs)) remindNameViolation(v);
  } catch (e) {
    log("NAME REMINDER TICK FAILED:", e.message);
  }
}

function auditNames(records) {
  const now = Date.now();
  const out = new Map();
  for (const r of records) {
    const refs = r.refs || {};
    if (!refs.board) continue;
    // 传进来的应是**未归一**的记录：老记录用文件里的原文，新记录用 refs.rawFrom
    const raw = refs.rawFrom || String(r.from || "");
    const mapped = boardName(raw);
    if (!raw || raw === mapped) continue;
    const at = parseCst(r.ts);
    if (!at || at < NAME_AUDIT_SINCE || now - at > NAME_AUDIT_MS) continue;
    const cur = out.get(raw) || { raw, mapped, count: 0, lastTs: r.ts };
    cur.count++;
    if (String(r.ts) > String(cur.lastTs)) cur.lastTs = r.ts;
    out.set(raw, cur);
  }
  return [...out.values()].sort((a, b) => b.count - a.count);
}

function stamp() {
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(new Date());
  const get = (t) => (parts.find((x) => x.type === t) || {}).value || "";
  return get("year") + get("month") + get("day") + "_" + get("hour") + get("minute") + get("second");
}

function writeTaskFile(name, obj) {
  try {
    fs.mkdirSync(INBOX_DIR, { recursive: true });
    const file = path.join(INBOX_DIR, name);
    if (fs.existsSync(file)) return false;
    fs.writeFileSync(file, JSON.stringify(obj, null, 2), "utf8");
    log("INBOX TASK DROPPED", name);
    return true;
  } catch (e) {
    log("INBOX WRITE FAILED:", e.message);
    return false;
  }
}

function queueDshFromBoard(entry) {
  const alias = resolveTarget(entry.target);
  const fname = "board_" + slugFor(alias) + "_" + stamp() + ".task.json";
  const canonical = {
    ts: entry.time.replace(" ", "T") + ":00+08:00",
    from: entry.author,
    to: alias,
    channel: "board",
    kind: "message",
    body: entry.content,
    state: "open",
  };
  const ok = writeTaskFile(fname, {
    schema: "dialog.v1",
    to: alias,
    instance: alias,
    claimedBy: alias,
    state: "dispatched",
    from: CODEX_SERVICE,
    target: "shared-board",
    canonical,
    context: dialogContextText(),
    do: `你是 ${alias}。老板在共享看板 docs/COMMS_BOARD.md 给你留言（${entry.time}）：${entry.content}。请处理，并把回复写回看板，署名用 ${alias}，格式：- @老板 时间 ${alias}：内容。`,
    why: `看板 @${entry.target} 留言转投 inbox，指派 ${alias}（Codex 托管转发；dialog.v1 + 最近对话切片；claimedBy=${alias}）`,
    accept: true,
  });
  // 成功时**不再回一行**：那只是回声，而且常常比对方本人的回复还早，看起来像刷屏
  // （2026-09-10 老板反馈）。派单状态由 Hub 里的 inbox 任务记录以细行呈现，失败才说话。
  if (!ok) {
    appendBoardLine("老板", CODEX_SERVICE, "（尝试把 @" + entry.target + " 留言转投 inbox 失败，请稍后重试或直接在对应 dsh 会话里说。）");
  } else {
    log("DISPATCH SILENT OK", fname, "->", alias);
  }
}

function hmNow() {
  const d = new Date();
  return d.getHours() * 60 + d.getMinutes();
}

function heartAgeSec() {
  try {
    return (Date.now() - fs.statSync(HEART_FILE).mtimeMs) / 1000;
  } catch {
    return 1e6;
  }
}

function checkTimeline() {
  const d = new Date();
  if (d.getDay() > 4) return;
  if (haltActive()) return; // HUB-006：暂停期间不按点唤醒（自动唤醒属于"停"的清单）
  const m = hmNow();
  const dateStr = fmtNow().slice(0, 10);
  const st = readState();
  const done = st.dispatchDone || {};

  for (const ev of WATCH_EVENTS) {
    const [h, mi] = ev.split(":").map(Number);
    const em = h * 60 + mi;
    if (m >= em && m < em + 8) {
      const key = dateStr + "|" + ev;
      if (!done[key]) {
        const hhmm = ev.replace(":", "");
        const ok = writeTaskFile("wake_dsh_" + dateStr.replace(/-/g, "") + "_" + hhmm + ".task.json", {
          schema: "dialog.v1",
          to: resolveTarget("dsh"),
          instance: resolveTarget("dsh"),
          claimedBy: resolveTarget("dsh"),
          state: "dispatched",
          from: CODEX_SERVICE,
          target: "wake-timeline",
          context: dialogContextText(),
          do: `现在是 ${ev}，按 duty/schedule.yaml 开始/继续今天的守盘工作。处理后在共享看板回一行状态给老板（格式：- @老板 时间 ${resolveTarget("dsh")}：状态），并把本任务移到 outputs/inbox/done/。`,
          why: "watch_bridge 时间轴唤醒（Codex 托管派单）",
          event: ev,
          date: dateStr,
          accept: true,
        });
        if (ok) {
          done[key] = true;
          writeState({ ...st, dispatchDone: done });
          log("DISPATCH EVENT", ev, "task dropped");
        }
      }
    }
  }

  const age = heartAgeSec();
  const last = Number(st.lastHeartbeatWarnAt || 0);
  if (age > 150 && Date.now() - last > 10 * 60 * 1000) {
    const ok = writeTaskFile("wake_dsh_heartbeat_" + stamp() + ".task.json", {
      schema: "dialog.v1",
      to: resolveTarget("dsh"),
      instance: resolveTarget("dsh"),
      claimedBy: resolveTarget("dsh"),
      state: "dispatched",
      from: CODEX_SERVICE,
      target: "wake-heartbeat",
      context: dialogContextText(),
      do: `值守引擎心跳已中断 ${Math.round(age)} 秒，请立即检查 duty/duty_engine.py 是否还活着，处理后回写看板并把本任务移到 outputs/inbox/done/。`,
      why: "引擎心跳中断应急唤醒（Codex 托管派单）",
      accept: true,
    });
    if (ok) writeState({ ...readState(), lastHeartbeatWarnAt: Date.now() });
  }
}

async function respondToNewEntries() {
  if (busy) {
    boardTimer = setTimeout(respondToNewEntries, 3000);
    return;
  }
  // “新行” = 对应的 dialog 记录还不存在。入库与路由共用同一套 id 去重，
  // 所以不再依赖字节偏移：别人在文件中间插行/原地改行都不会再漏（2026-09-10 真丢过一条）。
  let full = "";
  try {
    full = fs.readFileSync(BOARD_FILE, "utf8");
  } catch {
    return;
  }
  const fresh = [];
  for (const line of full.split("\n")) {
    const entry = entryFromBoardLine(line);
    if (!entry) continue;
    const rec = dialogRecordFromBoardLine(entry.line);
    if (!rec) continue;
    appendDialog(rec); // 入库（重复自动跳过）
    if (routedIds.has(rec.id)) continue;
    routedIds.add(rec.id); // 先记账再处理：宁可漏一次，也不要重复派单
    fresh.push(entry);
  }
  if (!fresh.length) return;
  saveRoutedIds();

  for (let fi = 0; fi < fresh.length; fi++) {
      const entry = fresh[fi];
      const authorLow = entry.author.toLowerCase();
      // ── HUB-006：解除暂停 = **老板的公告**（放在最前，连 codex 线的行也要被审！）──
      if (/^\s*【解除暂停】/.test(String(entry.content || ""))) {
        if (String(entry.author) === "老板") {
          clearHalt("老板", "看板公告 " + entry.time + "：" + String(entry.content).slice(0, 60));
        } else {
          appendBoardLine("老板", CODEX_SERVICE,
            "（系统：@" + entry.author + " 那条『解除暂停』**不生效**——只有老板本人发的公告才算。当前仍是暂停态。）");
          log("HALT CLEAR REJECTED:", entry.author);
        }
        continue;
      }
      // 公告（@全体）——**2026-09-12 重做**：老板要求"公告必须回复收到"、"已回执的也要回执"。
      //   所以公告不再"只入库"：
      //     ① 投到**每条注册线的信箱**（附短号与回执写法）；
      //     ② **尽力叫醒**（queue 优先，带 90 秒冷却/每小时上限，天然限流）；
      //     ③ 回执口径见 applyNoticeAcks：**必须带指向**（短号 / 时间 / 引用回复），裸词不算。
      if (boardName(entry.target) === "全体") {
        const rec = dialogRecordFromBoardLine(entry.line);
        const code = rec ? noticeCode(rec.id) : "";
        const authorAlias = boardName(entry.author);
        const lines = Object.keys(readAgents().agents || {});
        let sent = 0;
        const delivered = []; // HUB-015(b)：记下"投递给它"的时刻（回执计时起点）
        for (const alias of lines) {
          if (alias === authorAlias || alias === "老板") continue;
          if (String(agentFor(alias).status || "").toLowerCase() === "retired") continue;
          const tip =
            "【公告 " + code + "】" + entry.content +
            "\n\n请回执：在看板回一行 `收到 " + code + "`（或点引用回复这条公告再回「收到」）。**每条公告都要单独回执**。";
          try {
            fs.appendFileSync(path.join(MAILBOX_DIR, "pending_" + slugFor(alias) + ".ndjson"), JSON.stringify({ ts: fmtNow(), from: authorAlias, to: alias, body: tip }) + "\n", "utf8");
            delivered.push(alias);
          } catch {}
          try {
            const dv = await deliverByQueue(alias, "（公告 " + code + " 投递提示 · 来自 " + authorAlias + "）" + tip.slice(0, 200));
            if (dv.ok) sent++;
          } catch {}
        }
        if (rec && rec.id) markNoticeDelivered(rec.id, delivered);
        log("NOTICE INGESTED:", authorAlias, code, "投信箱=" + (lines.length - 1) + " 叫醒=" + sent);
        continue;
      }
      // 自己（codex-* 任何一条线）写的行不再当输入，避免自问自答
      // （**公告已在上面先处理**：公告是广播、不是回合，不该被这条规则跳过）
      if (/^codex([-_]|$)/i.test(authorLow)) continue;
      if (/^dsh/i.test(entry.target) && !/^dsh/i.test(authorLow)) {
        if (haltActive() && String(entry.author) !== "老板") {
          log("HALT: 暂停中，不派新活（dsh 目标）", entry.target);
          queueForThread(resolveTarget(entry.target), entry);
          continue;
        }
        queueDshFromBoard(entry);
        continue;
      }
      if (!/codex/i.test(entry.target)) continue;
      // 暂停期间：别自动唤醒/派活（老板本人的手令除外——他要能操作）
      if (haltActive() && String(entry.author) !== "老板") {
        queueForThread(resolveTarget(entry.target), entry);
        log("HALT: 暂停中，只落信箱不唤醒", entry.target);
        continue;
      }
    if (busy) {
      boardTimer = setTimeout(respondToNewEntries, 3000);
      return;
    }
      busy = true;
      try {
      const want = resolveTarget(entry.target);
        // HUB-013：旧工号（退役 slug）不再可投递——明确回一句，别静默丢
        const retiredOwner = retiredSlugOwner(entry.target);
        if (retiredOwner) {
          appendBoardLine("老板", CODEX_SERVICE,
            "（系统：`" + String(entry.target).replace(/^@/, "") + "` 是**退役工号**，不再投递；找这位请用岗位名 @" + retiredOwner + "（同名即现任）。）");
          log("RETIRED SLUG TARGET:", entry.target, "→ 岗位", retiredOwner);
          continue;
        }
        // 别名 ↔ 会话绑定：agents.json 里配了 threadId 的线，直接投进它自己的会话（老板要求
        // “@谁就是找谁”）。忙/失败不再代答：撤回记账、留队重试，服务只发状态行。
          const promptText =
            "（看板留言，来自 " + entry.author + "，时间 " + entry.time + "）" + entry.content;
          // ★ HUB-002：先判定（纯函数），再决定动作——**投不进绝不改投别人**
          const verdict = decideDelivery(want);
          log("DELIVER:", want, "action=" + verdict.action, "status=" + verdict.status,
            verdict.reason || "", "lastOut=" + verdict.lastOutputSec + "s", "wakes1h=" + verdict.wakesLastHour);
          if (verdict.action === "inject") {
            // ★ REQ-HUB-004b：首选 `codex queue`（穿透写锁，秒级唤醒），resume 退成备选
            const dv = await deliverToLine(want, promptText);
            if (dv.ok) {
              setWakeBook(want, {
                history: [...((wakeBook(want).history) || []), Date.now()].slice(-50),
                attempts: 0,
                nextAt: 0,
                lastAt: Date.now(),
              });
              // queue 路径没有回复（本人会被叫起来自己回，所以不预置回声，免得刷屏）；
              // resume 路径本身带回复，照旧贴上。
              if (dv.reply) appendBoardLine("老板", want, dv.reply);
            } else if (dv.how === "no-thread") {
              queueForThread(want, entry);
              appendBoardLine("老板", CODEX_SERVICE, "（系统：@" + want + " 没有绑定会话，已落信箱。）");
              log("NO THREAD → 落信箱:", want);
            } else {
              const e = new Error(dv.error || "投递失败");
              queueForThread(want, entry);
              // 无论哪种失败，留言先保住（绝不丢、绝不转别人），再分类处理
              const kind = classifyInjectFailure(e, verdict);
              if (kind === "window-idle") {
                setWakeBook(want, { nextAt: 0, attempts: 0, windowIdle: true, lastError: String(e.message).slice(0, 120), lastAt: Date.now() });
                if (dutyLines().includes(want)) {
                  // 有值守 → 交给**它自己那条值守分线**做检索式代答（服务不替它说话）
                  log("WINDOW IDLE → 交本线值守（检索式代答）:", want, String(e.message).slice(0, 80));
                } else {
                  setWakeBook(want, { nextAt: 0, attempts: 0, done: true, parked: true, parkedAt: Date.now(), lastReason: "窗口占用但空闲（抢锁失败）" });
                  log("WINDOW IDLE (无值守) → 已投递未唤醒 + 停手:", want, String(e.message).slice(0, 80));
                  annotateNotWoken(want, "桌面端占着这条线的窗口、但没在跑回合（抢锁失败）");
                }
              } else {
                // 真在跑回合 / 其它失败 → 当忙，退避重试 2→5→15 分钟，不许轰炸
                const n = Number(wakeBook(want).attempts || 0);
                const wait = WAKE_BACKOFF_MS[Math.min(n, WAKE_BACKOFF_MS.length - 1)];
                setWakeBook(want, { attempts: n + 1, nextAt: Date.now() + wait, lastError: String(e.message).slice(0, 120), lastAt: Date.now() });
                log("INJECT FAILED → 判忙退避", want, Math.round(wait / 60000) + "分钟", String(e.message).slice(0, 80));
              }
            }
          } else if (verdict.action === "mailbox" || verdict.action === "backoff") {
            // 在忙 / 退避窗口内：**只落它自己的信箱**，不改投、不代答。
            // ★ 口径修正（老板 2026-09-11 05:0x）：光落信箱 = 「永远叫不醒」——必须**同时排定补投**。
            //   忙的时候不打扰（不立刻注入），但退避到点后由 wakeRetryTick 补投一次；
            //   仍忙就继续按 2→5→15 分钟退避，最多 WAKE_MAX_ATTEMPTS 次，之后停手并留一行说明。
            queueForThread(want, entry);
            if (verdict.action === "mailbox") {
              const n = Number(wakeBook(want).attempts || 0);
              const wait = WAKE_BACKOFF_MS[Math.min(n, WAKE_BACKOFF_MS.length - 1)];
              setWakeBook(want, {
                attempts: n + 1,
                nextAt: Date.now() + wait,
                lastReason: verdict.reason || "busy",
                lastAt: Date.now(),
              });
              log("DEFERRED WAKE:", want, "补投排定 +" + Math.round(wait / 60000) + "分钟",
                "attempts=" + (n + 1) + "/" + WAKE_MAX_ATTEMPTS, verdict.reason || "");
            } else {
              log("BACKOFF HOLD:", want, verdict.reason || verdict.action);
            }
          } else if (verdict.action === "duty") {
            // 本尊不在（offline/stale/没绑定）→ 留言进它信箱。
            // ★ 服务**不代替任何线说话**：有值守的交给它自己的值守分线（检索式代答），
            //   没有值守的只发一条**署名服务自己**的系统事实，不冒充那条线。
            queueForThread(want, entry);
            if (dutyLines().includes(want)) {
              log("DUTY → 交本线值守（检索式代答）:", want);
            } else {
              appendBoardLine("老板", CODEX_SERVICE, "（系统：@" + want + " 本尊不在且无值守，留言已进它信箱，等它上线自读。）");
            }
          } else if (verdict.action === "retired") {
            appendBoardLine("老板", CODEX_SERVICE, "（@" + want + " 〔已退役〕不投递、不兜底；要复产见 HUB-001。）");
          } else if (verdict.action === "unknown") {
            queueForThread(want, entry);
            appendBoardLine("老板", CODEX_SERVICE, "（@" + want + " 〔尚未上岗〕留言已进它信箱，等它上岗自读。）");
          }
      } catch (err) {
        log("BOARD REPLY ERROR:", err.message);
        appendBoardLine(
          "老板",
          CODEX_SERVICE,
          "（回复失败：" + err.message + "。若这是复杂任务，请到 Codex 正式对话交办。）"
        );
    } finally {
      busy = false;
    }
  }
}

function scheduleCheck() {
  if (boardTimer) clearTimeout(boardTimer);
  boardTimer = setTimeout(respondToNewEntries, 800);
}

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
    // 关掉 keep-alive（见下）：手机端一条 POST 若撞上“服务端刚关掉的空闲连接”，
    // 浏览器不会重试 POST，表现就是按钮永久停在「发送中…」而服务端日志里什么都没有。
    "Connection": "close",
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => {
      data += c;
      if (data.length > 20000) {
        reject(new Error("内容太长"));
        req.destroy();
      }
    });
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

const PAGE = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<title>团队共享看板</title>
<style>
/* —— 尺寸/间距全部走变量：按屏宽自适应，手机上紧凑、大屏上舒展 —— */
:root{
  --bg:#0d1117;--panel:#161b22;--line:#30363d;--text:#e6edf3;--dim:#8b949e;--accent:#2f81f7;
  --codex:#3fb950;--dsh:#58a6ff;--boss:#ff7b72;--warn:#f0b847;
  --input-bg:#0d1117;--code-bg:#0b0f16;--warn-bg:#3a2a12;--mark-bg:#3a2f12;--flash-bg:#1f2a3d;
  --fs-msg:clamp(14px,3.9vw,15.5px);
  --fs-name:clamp(13.5px,3.9vw,15px);
  --fs-meta:clamp(11px,3.1vw,12.5px);
  --fs-ui:clamp(12.5px,3.6vw,14px);
  --fs-title:clamp(15px,4.2vw,17px);
  --pad-x:clamp(10px,3.2vw,15px);
  --gap:clamp(8px,2.4vw,12px);
  --r:clamp(10px,2.8vw,14px);
  --tap:44px;
}
/* —— 配色方案（参考成熟软件）：夜 / 白天(微信风) / 护眼(暖纸) / 墨蓝(Discord 风) —— */
body[data-theme="light"]{--bg:#ededed;--panel:#ffffff;--line:#dcdcdc;--text:#111111;--dim:#7a7a7a;--accent:#07c160;--codex:#0a7d3f;--dsh:#1a73e8;--boss:#e03e3e;--warn:#b26a00;--input-bg:#f7f7f7;--code-bg:#f2f2f2;--warn-bg:#fff4e0;--mark-bg:#fff2b8;--flash-bg:#eaf3ff}
body[data-theme="paper"]{--bg:#f5f0e3;--panel:#fffdf6;--line:#e0d7c2;--text:#3a3327;--dim:#8b8474;--accent:#c07a1e;--codex:#2f7d4f;--dsh:#2b6cb0;--boss:#c0392b;--warn:#9a6b12;--input-bg:#f1ebdc;--code-bg:#efe9da;--warn-bg:#f6e6c8;--mark-bg:#f6e2a8;--flash-bg:#eef3e2}
body[data-theme="slate"]{--bg:#1e1f22;--panel:#2b2d31;--line:#3f4147;--text:#dbdee1;--dim:#949ba4;--accent:#5865f2;--codex:#3ba55d;--dsh:#00a8fc;--boss:#ed4245;--warn:#faa81a;--input-bg:#1a1b1e;--code-bg:#16171a;--warn-bg:#3a2f18;--mark-bg:#3a3418;--flash-bg:#2b3350}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;display:flex;flex-direction:column;height:100dvh;overscroll-behavior:none;-webkit-text-size-adjust:100%}
/* —— 顶部：标题栏 + 可折叠面板。滚动看消息时自动收起，给消息让位（聊天软件的做法） —— */
#top{background:var(--panel);border-bottom:1px solid var(--line);flex-shrink:0}
#top.slim #panel{display:none}
header{display:flex;align-items:center;gap:var(--gap);padding:clamp(7px,2vw,11px) var(--pad-x)}
header h1{font-size:var(--fs-title);margin:0;font-weight:650;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer}
/* 顶栏那行小字必须能缩，否则窄屏会把右边按钮挤出屏幕（老板反馈"看不到小字"） */
#summary,#status{font-size:var(--fs-meta);color:var(--dim);flex-shrink:1;min-width:0;max-width:42vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#panelBtn{background:transparent;border:1px solid var(--line);color:var(--dim);border-radius:9px;min-width:38px;min-height:34px;font-size:15px;cursor:pointer;flex-shrink:0}
#panelBtn.on{color:var(--accent);border-color:var(--accent)}
#panel{display:flex;flex-direction:column}
#agents{display:flex;gap:6px;padding:0 var(--pad-x) 8px;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch}
/* 微信式顶部群组条：横滑；末尾一枚「＋ 添加」（老板 2026-09-12 01:0x） */
#groups{display:flex;gap:6px;padding:6px var(--pad-x) 2px;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch}
#groups::-webkit-scrollbar{display:none}
.gchip{display:flex;gap:5px;align-items:center;border:1px solid var(--line);border-radius:999px;padding:4px 10px;color:var(--dim);font-size:var(--fs-ui);white-space:nowrap;flex-shrink:0;cursor:pointer;background:var(--input-bg)}
.gchip.on{border-color:var(--accent);color:var(--accent)}
.gchip.add{border-style:dashed}
/* HUB-003 置顶条：「待老板：N 条」——打开页面一眼看到"要他做什么" */
#bossBar{display:flex;gap:6px;align-items:center;padding:7px var(--pad-x);font-size:var(--fs-ui);background:#3a2a12;color:#f0b45a;border-bottom:1px solid #5a3f18}
#bossBar.off{display:none}
#bossBar.muted{background:#2a2a2a;color:var(--dim)}
#bossBar b{font-weight:700}
#bossBar .grow{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#bossBar button{background:transparent;border:1px solid currentColor;color:inherit;border-radius:8px;padding:3px 8px;font-size:var(--fs-ui);cursor:pointer;flex-shrink:0}
/* HUB-006 暂停闸：红条「已暂停·等老板」/ 绿条「已恢复·老板 <时间>」——打开页面第一眼就看到 */
#haltBar{display:flex;gap:6px;align-items:center;padding:7px var(--pad-x);font-size:var(--fs-ui);border-bottom:1px solid}
#haltBar.off{display:none}
#haltBar.halt{background:#3d1418;color:#ff7b72;border-color:#5c2126}
#haltBar.resumed{background:#12261a;color:#3fb950;border-color:#1d3a27}
#haltBar b{font-weight:700;flex-shrink:0}
#haltBar .grow2{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#bossList{display:none;padding:0 var(--pad-x) 8px;background:#2a1f0f;color:var(--text);font-size:var(--fs-ui)}
#bossList.on{display:block}
#bossList .row{padding:6px 0;border-top:1px solid var(--line)}
#bossList .k{color:#f0b45a;font-weight:600}
#agents::-webkit-scrollbar{display:none}
.chip{display:flex;gap:5px;align-items:center;border:1px solid var(--line);border-radius:999px;padding:5px 10px;color:var(--dim);font-size:var(--fs-ui);white-space:nowrap;flex-shrink:0;cursor:pointer;background:var(--input-bg)}
.chip b{font-weight:600}
.chip.open{border-color:#f0883e;color:#f0883e}
.chip.retired{border-style:dashed;opacity:.55} /* HUB-013：退役的线灰显虚线边，仍在（可追溯），不参与在岗 */
.chip span.mail{color:#f0883e;font-weight:600}
.chip.online{border-color:var(--codex);color:var(--codex)}
.chip.sel{border-color:var(--accent);color:var(--accent)}
.chip,.name{-webkit-touch-callout:none;user-select:none}
#warn{display:none;align-items:flex-start;gap:8px;padding:6px var(--pad-x);background:var(--warn-bg);color:var(--warn);font-size:var(--fs-meta);line-height:1.6}
#warn.on{display:flex}
#warnText{flex:1}
#warnX{background:transparent;border:1px solid #5c4318;color:var(--warn);border-radius:6px;padding:0 7px;font-size:var(--fs-meta);cursor:pointer;flex-shrink:0}
#tools{display:flex;gap:8px;align-items:center;padding:0 var(--pad-x) 9px;font-size:var(--fs-ui)}
#modes{display:flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;flex-shrink:0}
#modes button{background:transparent;color:var(--dim);border:0;padding:6px 11px;font-size:var(--fs-ui);cursor:pointer}
#modes button.on{background:var(--accent);color:#fff}
#searchWrap{flex:1;min-width:0;display:none}
#searchWrap.on{display:flex}
#search{width:100%;min-width:0;background:var(--input-bg);color:var(--text);border:1px solid var(--line);border-radius:9px;padding:7px 10px;font-size:var(--fs-ui)}
#tools .ico{background:transparent;color:var(--dim);border:1px solid var(--line);border-radius:9px;padding:6px 9px;font-size:var(--fs-ui);cursor:pointer;flex-shrink:0}
#notifyBtn.on{color:var(--codex);border-color:var(--codex)}
/* —— 消息流 —— */
#board{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:var(--gap) var(--pad-x) 18px;display:flex;flex-direction:column;gap:clamp(9px,2.6vw,14px)}
.day{display:flex;align-items:center;gap:10px;color:var(--dim);font-size:var(--fs-meta)}
.day::before,.day::after{content:"";flex:1;height:1px;background:var(--line)}
.title{font-size:calc(var(--fs-title) + 2px);font-weight:700;color:var(--text)}
.note{color:var(--dim);font-size:var(--fs-ui);line-height:1.7}
.entry{display:flex;flex-direction:column;gap:4px;max-width:100%}
.entry .meta{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.entry .name{font-weight:650;font-size:var(--fs-name)}
.entry .time{font-size:var(--fs-meta);color:var(--dim)}
/* 统一气泡：同一套底、同一套圆角与内边距；**只靠彩色边分左右** */
.bubble{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--line);border-right:1px solid var(--line);border-radius:var(--r);padding:clamp(6px,1.8vw,9px) clamp(9px,2.6vw,12px);font-size:var(--fs-msg);line-height:1.66;white-space:pre-wrap;overflow-wrap:anywhere;max-width:min(86%,38em);cursor:pointer}
/* 老板自己的发言靠右（像聊天软件里“我说的话”）：同一个气泡，彩色边镜像到右边 */
.entry.me{align-items:flex-end}
.entry.me .meta{justify-content:flex-end}
.entry.me .bubble{border-left:1px solid var(--line);border-right:3px solid var(--boss)}
.c-codex{color:var(--codex)}
.c-boss{color:var(--boss)}
.c-dsh{color:var(--dsh)}
/* 彩色边：**左边发的消息，彩边在左**（绿=codex / 蓝=dsh / 红=老板）；
   老板自己的消息靠右，所以彩边镜像到右边（红）。老板 2026-09-10 23:5x 澄清：
   "只有我是红的"= 只有他的边是红色，别人的彩边要保留，不是不要。 */
.b-codex{border-left-color:var(--codex)}
.b-boss{border-left-color:var(--boss)}
.b-dsh{border-left-color:var(--dsh)}
.prog{display:flex;gap:7px;align-items:baseline;padding:1px 0 1px 10px;border-left:3px solid var(--line);color:var(--dim);font-size:var(--fs-meta);font-style:italic;line-height:1.55}
.prog-tag{flex-shrink:0;color:#6e7681;border:1px solid var(--line);border-radius:6px;padding:0 5px;font-style:normal;font-size:var(--fs-meta)}
.prog-time{flex-shrink:0;color:#6e7681}
.prog-body{word-break:break-word}
.state{flex-shrink:0;border:1px solid var(--line);border-radius:6px;padding:0 6px;font-size:calc(var(--fs-meta) - .5px)}
.state.s-dispatched{color:#d29922;border-color:#9e6a03}
.state.s-todo{color:#0d1117;background:#f0883e;border-color:#f0883e;font-weight:700}
.state.s-done{color:#6e7681}
.chan{flex-shrink:0;color:#6e7681;border:1px dashed var(--line);border-radius:6px;padding:0 5px;font-size:calc(var(--fs-meta) - 1px)}
.qbtn{background:transparent;border:1px solid var(--line);color:var(--dim);border-radius:6px;padding:0 6px;font-size:calc(var(--fs-meta) - 1px);cursor:pointer}
.quote{background:var(--code-bg);border-left:3px solid #6e7681;border-radius:6px;padding:5px 9px;margin:0 0 2px 6px;color:var(--dim);font-size:var(--fs-meta);white-space:pre-wrap;word-break:break-word}
.empty{color:var(--dim);font-size:var(--fs-ui);text-align:center;padding:24px 10px}
/* —— 输入区：默认只占一行，引用/前缀提示才展开 —— */
#composer{flex-shrink:0;background:var(--panel);border-top:1px solid var(--line);padding:clamp(8px,2.4vw,12px) var(--pad-x);padding-bottom:calc(clamp(8px,2.4vw,12px) + env(safe-area-inset-bottom));display:flex;flex-direction:column;gap:8px}
#route{display:flex;align-items:center;gap:7px;font-size:var(--fs-ui);color:var(--dim)}
#route .rlabel{flex-shrink:0}
#targetSel{background:var(--input-bg);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:6px 8px;font-size:var(--fs-ui)}
#targetSel.overridden{opacity:.5}
#routeHint{display:none;flex-basis:100%;color:var(--dim);font-size:var(--fs-meta)}
#quote{display:none;align-items:flex-start;gap:8px;background:var(--input-bg);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:8px;padding:7px 9px;font-size:var(--fs-meta);color:var(--dim)}
#quote span{flex:1;white-space:pre-wrap;word-break:break-word;max-height:60px;overflow:hidden}
#quote button{background:transparent;border:0;color:var(--dim);font-size:16px;cursor:pointer;padding:0 4px}
#msg{background:var(--input-bg);color:var(--text);border:1px solid var(--line);border-radius:var(--r);padding:10px 12px;font-size:var(--fs-msg);line-height:1.6;min-height:var(--tap);max-height:120px;resize:none;font-family:inherit}
#send{background:var(--accent);color:#fff;border:0;border-radius:999px;min-height:var(--tap);font-size:var(--fs-ui);font-weight:600;cursor:pointer}
#send:active{opacity:.85}
 /* 消息提醒气泡：原来是一枚 accent 色的大胶囊（白天主题下就是一大块微信绿），老板嫌丑。
    改成"跟着当前配色走"的圆角方框：面板底 + 细边 + 左边一条 accent，字用正文色。 */
 #toast{position:fixed;left:50%;transform:translateX(-50%);bottom:calc(88px + env(safe-area-inset-bottom));
   background:var(--panel);color:var(--text);border:1px solid var(--line);border-left:3px solid var(--accent);
   border-radius:var(--r);padding:9px 13px;font-size:var(--fs-ui);max-width:86vw;display:none;z-index:9;
   box-shadow:0 6px 20px rgba(0,0,0,.35)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
/* —— 扁平化图标按钮（不上色，只用描边） —— */
.icon{display:flex;align-items:center;justify-content:center;background:transparent;border:1px solid var(--line);color:var(--dim);border-radius:9px;min-width:34px;min-height:32px;cursor:pointer;padding:0 6px}
.icon svg{display:block}
.icon.on{color:var(--text);border-color:var(--dim)}
/* —— 更多菜单 —— */
#menu{display:none;position:absolute;right:var(--pad-x);top:calc(env(safe-area-inset-top) + 46px);z-index:30;background:var(--panel);border:1px solid var(--line);border-radius:var(--r);box-shadow:0 10px 28px rgba(0,0,0,.5);overflow:hidden;min-width:172px}
#menu.on{display:block}
.mrow{display:block;width:100%;text-align:left;background:transparent;border:0;border-bottom:1px solid var(--line);color:var(--text);font-size:var(--fs-ui);padding:11px 14px;cursor:pointer}
.mrow:last-child{border-bottom:0}
.mrow.on{color:var(--accent)}
#menuTheme{display:flex;align-items:center;justify-content:space-between;gap:10px;cursor:default}
#themeDots{display:flex;gap:6px}
.dot{width:18px;height:18px;border-radius:50%;border:2px solid var(--line);cursor:pointer;display:inline-block}
.dot.on{border-color:var(--accent)}
/* —— 消息区外壳 + 右下角悬浮（回到底部 / 新消息扁条） —— */
/* 消息区必须待在**普通流**里：早先版本把它做成 position:absolute + inset:0，
   一旦外层高度不确定（老浏览器/怪异环境下）整块就塌成 0 高度，表现为"只剩顶栏和输入框"。
   现在：外壳是 flex 容器，消息区照旧 flex:1 自己滚；右下角控件用绝对定位挂在外壳上。 */
#boardWrap{flex:1 1 auto;min-height:44vh;position:relative;display:flex;flex-direction:column}
#board{flex:1 1 auto;min-height:0;overflow-y:auto}
#floaters{position:absolute;right:10px;bottom:10px;display:flex;align-items:center;gap:6px;z-index:8;pointer-events:none}
#floaters>*{pointer-events:auto}
#jump{display:none;background:var(--panel);border-radius:999px;min-width:38px;min-height:38px;box-shadow:0 4px 14px rgba(0,0,0,.4)}
#jump.on{display:flex}
/* 新消息提示：扁平一条，只给首行 + 省略号 */
#newPill{display:none;align-items:center;max-width:min(62vw,320px);background:var(--panel);border:1px solid var(--line);border-radius:999px;color:var(--dim);font-size:var(--fs-meta);padding:8px 12px;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.4)}
#newPill.on{display:flex}
#newPillText{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* —— 搜索页（模仿微信：独立页面 + 顶部搜索框 + 结果列表） —— */
#searchPage{display:none;position:fixed;inset:0;z-index:40;background:var(--bg);flex-direction:column}
#searchPage.on{display:flex}
#searchBar{display:flex;align-items:center;gap:8px;padding:calc(env(safe-area-inset-top) + 8px) var(--pad-x) 8px;background:var(--panel);border-bottom:1px solid var(--line);color:var(--dim)}
#searchInput{flex:1;min-width:0;background:var(--input-bg);color:var(--text);border:1px solid var(--line);border-radius:9px;padding:8px 11px;font-size:var(--fs-ui)}
#searchCancel{background:transparent;border:0;color:var(--accent);font-size:var(--fs-ui);cursor:pointer;padding:6px 2px}
#searchResults{flex:1;overflow-y:auto;overscroll-behavior:contain;padding:6px 0 20px}
.sres{display:flex;flex-direction:column;gap:2px;padding:10px var(--pad-x);border-bottom:1px solid var(--line);cursor:pointer}
.sres .n{font-size:var(--fs-name);font-weight:600}
.sres .t{font-size:var(--fs-meta);color:var(--dim)}
.sres .b{font-size:var(--fs-ui);color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sres .b em{background:var(--mark-bg);color:var(--warn);font-style:normal}
.sempty{color:var(--dim);font-size:var(--fs-ui);text-align:center;padding:26px 10px}
/* 从搜索结果跳到的消息，闪一下好找 */
@keyframes flash{0%,100%{background:transparent}30%{background:var(--flash-bg)}}
.flash .bubble{animation:flash 1.4s ease-in-out 1}
/* —— 输入区压到一行：左“发给” / 中“输入” / 右“发送” —— */
#composer{gap:6px}
#composerRow{display:flex;align-items:flex-end;gap:6px}
#targetSel{flex-shrink:0;max-width:38vw;background:transparent;border:1px solid var(--line);border-radius:999px;color:var(--dim);padding:8px 8px;font-size:var(--fs-meta)}
/* 输入框：压成一行；右边那条滚动条藏掉（老板 2026-09-11 08:5x 要求）——内容照样能滚 */
#msg{flex:1;min-width:0;min-height:36px;max-height:96px;padding:8px 11px;font-size:var(--fs-ui);border-radius:var(--r);scrollbar-width:none;-ms-overflow-style:none}
#msg::-webkit-scrollbar{width:0;height:0;display:none}
#send{flex-shrink:0;min-height:36px;min-width:62px;padding:0 14px;border-radius:999px;font-size:var(--fs-ui)}
#routeHint{padding:0 2px}
/* 诊断行：放在输入框正上方——只要你能看到输入框，就一定能看到它 */
#diag{font-size:var(--fs-meta);color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* 代码相关的内容单独成块（参考 Codex 自己的聊天：等宽 + 深底 + 可横滚），跟纯文字一眼分开 */
.bubble .code{background:var(--code-bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin:6px 0;overflow-x:auto;white-space:pre;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Courier New",monospace;font-size:calc(var(--fs-msg) - 2px);line-height:1.55}
.bubble .code code{font-family:inherit;white-space:pre}
.bubble .code-lang{display:block;color:var(--dim);font-family:inherit;font-size:var(--fs-meta);margin-bottom:4px}
.bubble .ic{background:var(--code-bg);border:1px solid var(--line);border-radius:5px;padding:0 4px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Courier New",monospace;font-size:calc(var(--fs-msg) - 2px);white-space:pre-wrap;word-break:break-all}
/* 行首标签（〔代答〕等）：一枚小牌，不占正文 */
.bubble .tag{display:inline-block;background:var(--code-bg);border:1px solid var(--line);border-radius:999px;padding:0 7px;margin-right:5px;font-size:calc(var(--fs-msg) - 3px);color:var(--dim);vertical-align:1px}
/* —— 头像（由看板名稳定派生：首字 + 色相）；不引外链、不存文件 —— */
.av{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;flex-shrink:0;color:#fff;font-weight:700;font-size:11px;line-height:1;user-select:none}
.av.lg{width:38px;height:38px;font-size:15px}
.av.sm{width:18px;height:18px;font-size:9px}
.row .av,.entry .av{margin-right:6px}
/* —— 联系人页（与搜索页同一套语言：整屏 + 顶部条 + 列表） —— */
#contactsPage{display:none;position:fixed;inset:0;z-index:40;background:var(--bg);flex-direction:column}
#contactsPage.on{display:flex}
#contactsBar{display:flex;align-items:center;gap:8px;padding:calc(env(safe-area-inset-top) + 8px) var(--pad-x) 8px;background:var(--panel);border-bottom:1px solid var(--line)}
#contactsBar .ct-title{font-size:var(--fs-ui);font-weight:600;color:var(--text);flex-shrink:0}
#contactsFilter{flex:1;min-width:0;background:var(--input-bg);color:var(--text);border:1px solid var(--line);border-radius:9px;padding:7px 10px;font-size:var(--fs-ui)}
#contactsCancel{background:transparent;border:1px solid var(--line);color:var(--dim);border-radius:8px;padding:6px 10px;font-size:var(--fs-ui);cursor:pointer;flex-shrink:0}
#contactsList{flex:1;overflow-y:auto;overscroll-behavior:contain;padding:6px 0 20px}
/* 新建群组页：复用联系人页的骨架 */
#groupPage{display:none;position:fixed;inset:0;z-index:41;background:var(--bg);flex-direction:column}
#groupPage.on{display:flex}
#groupName{flex:1;min-width:0;background:var(--input-bg);color:var(--text);border:1px solid var(--line);border-radius:9px;padding:7px 10px;font-size:var(--fs-ui)}
#groupCancel,#groupCreate{background:transparent;border:1px solid var(--line);color:var(--dim);border-radius:8px;padding:6px 10px;font-size:var(--fs-ui);cursor:pointer;flex-shrink:0}
#groupCreate{border-color:var(--accent);color:var(--accent)}
#groupPick{flex:1;overflow-y:auto;overscroll-behavior:contain;padding:6px 0 20px}
/* 派单页（HUB-004）：老板选人 + 写要求 + 一键生成标准卡；结果区给三态（叫醒/未唤醒/落信箱） */
#taskPage{display:none;position:fixed;inset:0;z-index:43;background:var(--bg);flex-direction:column}
#taskPage.on{display:flex}
#taskBar{display:flex;align-items:center;gap:8px;padding:calc(env(safe-area-inset-top) + 8px) var(--pad-x) 8px;background:var(--panel);border-bottom:1px solid var(--line);flex-shrink:0}
#taskBar .ct-title{font-size:var(--fs-ui);font-weight:600;color:var(--text);flex:1}
#taskCancel{background:transparent;border:1px solid var(--line);color:var(--dim);border-radius:8px;padding:6px 10px;font-size:var(--fs-ui);cursor:pointer;flex-shrink:0}
#taskBody{flex:1;overflow-y:auto;overscroll-behavior:contain;padding:12px var(--pad-x) 28px}
.tp-f{margin-bottom:14px}
.tp-l{display:block;font-size:var(--fs-ui);color:var(--dim);margin-bottom:6px}
.tp-l .req{color:#e5484d}
#taskPage input,#taskPage textarea,#taskPage select{width:100%;box-sizing:border-box;background:var(--input-bg);color:var(--text);border:1px solid var(--line);border-radius:9px;padding:8px 10px;font-size:var(--fs-ui);font-family:inherit}
#taskPage textarea{min-height:62px;resize:vertical;line-height:1.5}
.tp-row{display:flex;gap:10px}
.tp-row>div{flex:1;min-width:0}
.tp-acc{display:flex;gap:8px;margin-bottom:6px}
.tp-acc input{flex:1;min-width:0}
.tp-del{background:transparent;border:1px solid var(--line);color:var(--dim);border-radius:9px;padding:0 10px;cursor:pointer;flex-shrink:0}
#taskAddAcc{width:100%;background:transparent;border:1px dashed var(--line);color:var(--dim);border-radius:9px;padding:7px 10px;font-size:var(--fs-ui);cursor:pointer}
#taskSubmit{width:100%;background:var(--accent);color:#fff;border:0;border-radius:11px;padding:12px;font-size:var(--fs-ui);cursor:pointer}
#taskSubmit:disabled{opacity:.5;cursor:default}
#taskResult{margin-top:4px}
.tp-res{background:var(--panel);border-left:3px solid var(--line);border-radius:10px;padding:10px 12px;font-size:var(--fs-ui);line-height:1.65}
.tp-res.ok{border-left-color:#2f9e44}
.tp-res.warn{border-left-color:#f59f00}
.tp-res.info{border-left-color:var(--accent)}
.tp-res .tp-id{font-weight:650}
.tp-res .tp-sub{display:block;margin-top:4px;color:var(--dim);font-size:var(--fs-meta)}
.gp{display:flex;align-items:center;gap:10px;padding:10px var(--pad-x);border-bottom:1px solid var(--line);cursor:pointer}
.gp.on{background:var(--flash-bg)}
.gp .gp-box{width:18px;height:18px;border:1px solid var(--line);border-radius:5px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:12px;color:var(--accent)}
.ct{display:flex;align-items:center;gap:10px;padding:10px var(--pad-x);cursor:pointer;border-bottom:1px solid var(--line)}
.ct:active{background:var(--input-bg)}
.ct .ct-main{flex:1;min-width:0}
.ct .ct-name{font-size:var(--fs-msg);color:var(--text);display:flex;align-items:center;gap:6px}
.ct .ct-sub{font-size:var(--fs-meta);color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}
.ct .ct-right{flex-shrink:0;text-align:right;font-size:var(--fs-meta);color:var(--dim)}
.ct .ct-badge{display:inline-block;min-width:18px;background:var(--warn);color:#231a05;border-radius:999px;padding:0 5px;font-weight:700}
/* 派单/桥任务的细行（比气泡小一号，别和对话抢注意力） */
.task-line{display:flex;gap:7px;align-items:baseline;padding:1px 0 1px 10px;border-left:3px solid var(--line);color:var(--dim);font-size:var(--fs-meta);line-height:1.55}
.task-line .tl-tag{flex-shrink:0;color:#6e7681;border:1px solid var(--line);border-radius:6px;padding:0 5px;font-size:var(--fs-meta)}
.task-line .tl-body{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.task-line .tl-body b{font-weight:600;color:var(--text)}
.task-line.s-todo .tl-tag{color:#0d1117;background:#f0883e;border-color:#f0883e;font-weight:700}
/* 公告：全宽卡片，一眼和对话区分（所有人可见、谁都不回） */
.notice{display:flex;flex-direction:column;gap:4px}
.notice .n-meta{display:flex;align-items:baseline;gap:8px;font-size:var(--fs-meta);color:var(--dim)}
.notice .n-tag{flex-shrink:0;border:1px solid var(--accent);color:var(--accent);border-radius:6px;padding:0 6px;font-weight:600}
.notice .n-body{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:var(--r);padding:clamp(7px,2vw,10px) clamp(10px,2.8vw,13px);font-size:var(--fs-msg);line-height:1.66;white-space:pre-wrap;overflow-wrap:anywhere}
.notice .n-ack{display:flex;flex-wrap:wrap;gap:8px;font-size:var(--fs-meta);color:var(--dim);padding-left:4px}
.notice .n-ack .ok{color:var(--codex)}
.notice .n-ack .no{color:#6e7681}
/* 兜底：万一 dvh/百分比高度都不认，至少让页面能滚起来，不至于"什么都没有" */
body{min-height:100vh}
#board{min-height:200px}
</style>
</head>
<body>
<script>
/* 版本守卫：独立于主脚本。主脚本万一初始化就抛错（表现就是"只剩顶栏和输入框、点不动"），
   这里仍然每 15 秒问一次服务，一旦服务端版本和自己不一致就整页刷新——手机端不必手动清缓存。 */
(function () {
  var V = "${PAGE_VER}";
  var errs = [];
  function el() {
    try {
      return document.getElementById("status");
    } catch (e) {
      return null;
    }
  }
  function diagEl() {
    try {
      return document.getElementById("diag");
    } catch (e) {
      return null;
    }
  }
  function setBoth(text, warn) {
    [el(), diagEl()].forEach(function (n) {
      if (!n) return;
      n.textContent = text;
      if (warn) n.style.color = "#f0b847";
    });
  }
  // 主脚本挂掉时，守卫替它上报（这条最重要：页面变成"只剩顶栏和输入框"就是它）
  function report(payload) {
    try {
      payload.ver = V;
      payload.guard = true;
      fetch("/api/uireport", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }).catch(function () {});
    } catch (e) {}
  }
  // 把错误直接写到顶栏那行小字里：手机上看不到控制台，这行就是"病历"
  function paint() {
    if (!errs.length) return;
    try {
      setBoth("页面出错：" + errs[errs.length - 1], true);
      report({ ok: false, pageError: errs[errs.length - 1], allErrs: errs.slice(-3) });
    } catch (e) {}
  }
  window.addEventListener("error", function (e) {
    try { errs.push((e.message || "error") + (e.lineno ? " @" + e.lineno : "")); } catch (x) {}
    paint();
  });
  window.addEventListener("unhandledrejection", function (e) {
    try { errs.push("promise: " + ((e.reason && e.reason.message) || e.reason)); } catch (x) {}
    paint();
  });
  function boot() {
    var s = el();
    var d = diagEl();
    if (s && (!s.textContent || s.textContent === "…")) s.textContent = "v" + V.split(".").pop() + " · 载入中…";
    if (d && !d.textContent) d.textContent = "v" + V.split(".").pop() + " · 主脚本载入中…";
    paint();
  }
  if (document.readyState !== "loading") boot();
  else document.addEventListener("DOMContentLoaded", boot);
  // 主脚本若 4 秒内没把状态写成"已同步…"，就是它没跑起来
  setTimeout(function () {
    var s = el();
    var d = diagEl();
    if (d && /载入中/.test(d.textContent || "")) {
      setBoth("主脚本没起来" + (errs.length ? "：" + errs[0] : "（无报错）"), true);
      report({ ok: false, mainScript: "dead", allErrs: errs.slice(-3) });
    } else if (s && /载入中/.test(s.textContent || "")) {
      s.textContent = "v" + V.split(".").pop();
    }
  }, 4000);
  function ck() {
    try {
      fetch("/api/ping", { cache: "no-store" })
        .then(function (r) { return r.json(); })
        .then(function (p) { if (p && p.ver && p.ver !== V) location.reload(); })
        .catch(function () {});
    } catch (e) {}
  }
  ck();
  setInterval(ck, 15000);
})();
</script>
<div id="top">
  <header>
    <h1 id="titleBtn">团队共享看板</h1>
    <span id="summary"></span>
    <span id="status">…</span>
    <button id="menuBtn" class="icon" title="更多（搜索 / 提醒 / 面板）">
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/></svg>
    </button>
    <button id="panelBtn" class="on" title="收起 / 展开实例与筛选（收起后不会自己弹出来）">☰</button>
  </header>
  <div id="bossBar" class="off"></div>
  <div id="bossList"></div>
  <div id="haltBar" class="off"></div>
  <div id="panel">
    <div id="groups"></div>
    <div id="agents"></div>
    <div id="tools">
      <div id="modes">
        <button data-mode="all" class="on">全部</button>
        <button data-mode="todo">待办 <b id="todoN"></b></button>
        <button data-mode="unread">未读 <b id="unreadN"></b></button>
        <button data-mode="notice">公告 <b id="noticeN"></b></button>
      </div>
    </div>
  </div>
  <div id="warn"><span id="warnText"></span><button id="warnX" title="知道了（同样的旧账不再提示）">✕</button></div>
</div>
<div id="menu">
  <button class="mrow" id="menuTask">派单（生成标准卡）</button>
  <button class="mrow" id="menuContacts">联系人</button>
  <button class="mrow" id="menuSearch">搜索记录</button>
  <button class="mrow" id="menuNotify">新消息提醒：关</button>
  <button class="mrow" id="menuPanel">面板：自动收起</button>
  <button class="mrow" id="menuProgress">进度流：关</button>
  <div class="mrow" id="menuTheme"><span>配色</span><span id="themeDots"></span></div>
</div>
<div id="boardWrap">
  <div id="board"></div>
  <div id="floaters">
    <button id="newPill" title="有新消息，点一下到最新"><span id="newPillText"></span></button>
    <button id="jump" class="icon" title="到最新">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
    </button>
  </div>
</div>
<div id="toast"></div>
<div id="searchPage">
  <div id="searchBar">
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/></svg>
    <input id="searchInput" placeholder="搜索记录">
    <button id="searchCancel">取消</button>
  </div>
  <div id="searchResults"></div>
</div>
<div id="contactsPage">
  <div id="contactsBar">
    <span class="ct-title">联系人</span>
    <input id="contactsFilter" placeholder="搜索名字 / 职责">
    <button id="contactsCancel">取消</button>
  </div>
  <div id="contactsList"></div>
</div>
<div id="groupPage">
  <div id="contactsBar">
    <span class="ct-title">新建群组</span>
    <input id="groupName" placeholder="群名（2–40 字）">
    <button id="groupCancel">取消</button>
    <button id="groupCreate">创建</button>
  </div>
  <div id="groupPick"></div>
</div>
<div id="taskPage">
  <div id="taskBar">
    <span class="ct-title">派单</span>
    <button id="taskCancel">取消</button>
  </div>
  <div id="taskBody">
    <div class="tp-f">
      <label class="tp-l" for="taskAssignee">派给谁 <span class="req">*</span></label>
      <select id="taskAssignee"></select>
    </div>
    <div class="tp-f">
      <label class="tp-l" for="taskTitle">要什么（标题）<span class="req">*</span></label>
      <input id="taskTitle" placeholder="一句话说清要做什么（≥4 字）">
    </div>
    <div class="tp-f">
      <label class="tp-l" for="taskGoal">目标 / 背景</label>
      <textarea id="taskGoal" placeholder="为什么要做、做成什么样（可选）"></textarea>
    </div>
    <div class="tp-f">
      <label class="tp-l">验收标准 <span class="req">*</span>（至少一条；机器按它判）</label>
      <div id="taskAcc"></div>
      <button id="taskAddAcc" type="button">＋ 加一条</button>
    </div>
    <div class="tp-f tp-row">
      <div>
        <label class="tp-l" for="taskKind">类型</label>
        <select id="taskKind"></select>
      </div>
      <div>
        <label class="tp-l" for="taskPrio">优先级</label>
        <select id="taskPrio"></select>
      </div>
    </div>
    <div class="tp-f tp-row">
      <div>
        <label class="tp-l" for="taskPrefix">前缀（自动取号）</label>
        <select id="taskPrefix"></select>
      </div>
      <div>
        <label class="tp-l" for="taskDue">截止（可选）</label>
        <input id="taskDue" placeholder="如 2026-09-15 18:00">
      </div>
    </div>
    <div class="tp-f">
      <button id="taskSubmit" type="button">派单（生成卡 + 投信箱 + 看板留记录）</button>
    </div>
    <div class="tp-f" id="taskResult"></div>
  </div>
</div>
<div id="composer">
  <div id="diag"></div>
  <div id="quote"><span></span><button id="quoteX" title="取消引用">✕</button></div>
  <div id="routeHint"></div>
  <div id="composerRow">
    <select id="targetSel"></select>
    <textarea id="msg" rows="1" placeholder="发消息"></textarea>
    <button id="send">发送</button>
  </div>
</div>
<script>
const $=s=>document.querySelector(s);
// —— 头像：由看板名稳定派生（首字 + 色相）；服务端 /api/dialog 会下发同一份，缺了就本地算 ——
let AVATARS={};
function avHue(s){let h=0;const t=String(s||"?");for(let i=0;i<t.length;i++)h=(h*31+t.charCodeAt(i))%360;return h;}
function noticeCode(id){return "N-"+String(id||"").slice(0,4).toUpperCase();} // 与服务端同一算法
function avNode(alias,size){
  const el=document.createElement("span");
  const av=(alias&&AVATARS[alias])||null;
  const short=String(alias||"?").replace(/^(dsh|codex)-/,"");
  const m=short.match(/[A-Za-z0-9\u4e00-\u9fa5]/);
  el.className="av"+(size?" "+size:"");
  el.style.background="hsl("+((av&&typeof av.hue==="number")?av.hue:avHue(alias))+" 45% 42%)";
  el.textContent=(av&&av.text)?av.text:(m?m[0].toUpperCase():"?");
  el.title=String(alias||"");
  return el;
}
const boardEl=$("#board"),statusEl=$("#status"),msgEl=$("#msg"),sendEl=$("#send"),agentsEl=$("#agents");
const topEl=$("#top"),panelEl=$("#panel"),summaryEl=$("#summary");
// —— 面板折叠 ——
// 默认「自动」：往下翻消息收起、往上翻放出。
// 但**手动按过之后就锁住**：你不按，它不会自己弹出来（老板 2026-09-10 要求）。
let panelOpen=true;
let panelLocked=false;
let suppressAutoUntil=0; // 首屏自动滚到最新时，不要顺手把面板收起来（那是"程序滚动"，不是用户翻）
function setPanel(open,manual){
  panelOpen=!!open;
  if(manual)panelLocked=true;
  topEl.classList.toggle("slim",!panelOpen);
  // 便于无头验收脚本读内部状态（页面出错时也能一眼看出"以为是展开其实是收起"这种不同步）
  topEl.dataset.panel=(panelOpen?"1":"0")+(panelLocked?"L":"");
  $("#panelBtn").classList.toggle("on",panelOpen);
  $("#menuPanel").textContent="面板："+(panelLocked?(panelOpen?"已锁定展开":"已锁定收起"):"自动收起");
  syncTools();
}
function togglePanel(){setPanel(!panelOpen,true);}
function unlockPanel(){panelLocked=false;setPanel(true,false);}
// —— 更多菜单（搜索 / 提醒 / 面板） ——
// 配色方案（参考成熟软件）：夜=GitHub 深色；白天=微信风；护眼=暖纸；墨蓝=Discord 风
const THEMES=[["dark","夜","#0d1117","#e6edf3"],["light","白天","#ededed","#111111"],["paper","护眼","#f5f0e3","#3a3327"],["slate","墨蓝","#1e1f22","#dbdee1"]];
let THEME=(function(){
  try{
    const saved=localStorage.getItem("mchat_theme");
    if(saved)return saved;
  }catch(e){}
  try{return window.matchMedia&&window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";}catch(e){return "dark";}
})();
function renderThemeDots(){
  const box=$("#themeDots");
  if(!box)return;
  box.innerHTML="";
  for(const t of THEMES){
    const d=document.createElement("span");
    d.className="dot"+(t[0]===THEME?" on":"");
    d.title=t[1];
    d.style.background=t[2];
    d.style.borderColor=t[0]===THEME?"var(--accent)":t[3];
    d.addEventListener("click",()=>setTheme(t[0]));
    box.appendChild(d);
  }
}
function setTheme(t){
  THEME=t;
  document.body.dataset.theme=t;
  try{localStorage.setItem("mchat_theme",t);}catch(e){}
  renderThemeDots();
  toast("配色："+((THEMES.find(x=>x[0]===t)||[])[1]||t));
}
function setMenu(on){$("#menu").classList.toggle("on",!!on);}
function menuIsOpen(){return $("#menu").classList.contains("on");}
// —— 搜索页（微信式：独立界面 + 结果列表 + 点结果跳到那条） ——
function openSearch(){
  setMenu(false);
  $("#searchPage").classList.add("on");
  $("#searchInput").value="";
  renderSearch("");
  setTimeout(()=>{try{$("#searchInput").focus();}catch(e){}},50);
}
function closeSearch(){$("#searchPage").classList.remove("on");}
// —— 联系人页（HUB-009）：头像 + 名字 + 职责 + 状态/未读；点一条 = 把收件人切到它 ——
function openContacts(){
  setMenu(false);
  $("#contactsPage").classList.add("on");
  $("#contactsFilter").value="";
  renderContacts("");
  setTimeout(()=>{try{$("#contactsFilter").focus();}catch(e){}},50);
}
function closeContacts(){$("#contactsPage").classList.remove("on");}
// —— 群组（HUB-010）：顶部横滑群组条 + 「＋ 添加」；点一个群 = 只看这个群 —— 
let GROUPS=[];
function renderGroups(){
  const el=$("#groups");
  if(!el)return;
  el.innerHTML="";
  if(!(GROUPS||[]).length){
    // 一个群都没有时，仍留「＋ 添加」，别让人以为这功能不存在
    const add0=document.createElement("div");
    add0.className="gchip add";
    add0.textContent="＋ 添加群组";
    add0.addEventListener("click",openGroupPage);
    el.appendChild(add0);
    return;
  }
  for(const g of GROUPS){
    const c=document.createElement("div");
    c.className="gchip"+(FILTER.group===g.id?" on":"");
    c.appendChild(avNode(g.name,"sm"));
    const b=document.createElement("span");
    b.textContent=g.name+(g.members&&g.members.length?("（"+g.members.length+"）"):"");
    c.appendChild(b);
    c.title="只看这个群的消息；再点一下取消";
    c.addEventListener("click",()=>{
      FILTER.group=FILTER.group===g.id?null:g.id;
      renderGroups();
      renderDialog(CACHE);
      syncTools();
    });
    el.appendChild(c);
  }
  const add=document.createElement("div");
  add.className="gchip add";
  add.textContent="＋ 添加群组";
  add.addEventListener("click",openGroupPage);
  el.appendChild(add);
}
let PICKED=new Set();
function openGroupPage(){
  PICKED=new Set();
  $("#groupPage").classList.add("on");
  $("#groupName").value="";
  renderGroupPick();
  setTimeout(()=>{try{$("#groupName").focus();}catch(e){}},50);
}
function closeGroupPage(){$("#groupPage").classList.remove("on");}
function renderGroupPick(){
  const box=$("#groupPick");
  if(!box)return;
  box.innerHTML="";
  for(const a of (AGENTS||[])){
    const row=document.createElement("div");
    row.className="gp"+(PICKED.has(a.alias)?" on":"");
    const bx=document.createElement("span");
    bx.className="gp-box";
    bx.textContent=PICKED.has(a.alias)?"✓":"";
    row.appendChild(bx);
    row.appendChild(avNode(a.alias,"sm"));
    const main=document.createElement("div");
    main.className="ct-main";
    const nm=document.createElement("div");
    nm.className="ct-name";
    const b=document.createElement("b");
    b.textContent=a.alias;
    nm.appendChild(b);
    main.appendChild(nm);
    row.appendChild(main);
    row.addEventListener("click",()=>{
      if(PICKED.has(a.alias))PICKED.delete(a.alias);else PICKED.add(a.alias);
      renderGroupPick();
    });
    box.appendChild(row);
  }
}
async function createGroup(){
  const name=String($("#groupName").value||"").trim();
  if(name.length<2){toast("群名至少 2 字");return;}
  if(!PICKED.size){toast("至少选一个成员");return;}
  try{
    const r=await fetchT("/api/groups",{method:"POST",headers:{"Content-Type":"application/json","x-mchat-token":token},
      body:JSON.stringify({name:name,members:[...PICKED],by:"老板",source:"ui"})},12000);
    const j=await r.json();
    if(!r.ok){toast("建群失败："+String(j.error||r.status));return;}
    toast("已创建群组 "+name);
    closeGroupPage();
    load();
  }catch(e){toast("建群失败：网络/超时");}
}
// —— 派单页（HUB-004）：选人 + 写要求 + 一键生成标准卡 ——
//   规则全活在服务端（/api/tasks）：自动取号、套标准模板、投对方信箱、看板留一条派单记录，
//   并**返回三态投递结论**（叫醒 / 已投递未唤醒 / 已落信箱）。页面只做三件事：
//   给人用的表单、必填校验、把三态**原样**显示出来（不许自己编"已通知"）。
let TASK_META=null; // 前缀/类型/优先级：从 /api/meta 取（不写死在页面，登记表一改就跟着变）
function fillSel(sel,list,def){
  if(!sel||!Array.isArray(list))return;
  const keep=String(sel.value||"");
  sel.innerHTML="";
  for(const v of list){
    const o=document.createElement("option");
    o.value=String(v);o.textContent=String(v);
    sel.appendChild(o);
  }
  if(list.indexOf(keep)>=0)sel.value=keep;
  else if(def&&list.indexOf(def)>=0)sel.value=def;
  else if(list.length)sel.value=String(list[0]);
}
function taskMetaApply(m){
  if(!m)return;
  TASK_META=m;
  fillSel($("#taskKind"),m.taskKinds,"dev");
  fillSel($("#taskPrio"),m.taskPrios,"P2");
  fillSel($("#taskPrefix"),m.taskPrefixes,"HUB");
}
function taskRenderAssignees(){
  const sel=$("#taskAssignee");
  if(!sel)return;
  const keep=String(sel.value||"");
  sel.innerHTML="";
  const list=(AGENTS||[]).filter(a=>!a.retired).slice()
    .sort((a,b)=>String(a.alias).localeCompare(String(b.alias)));
  for(const a of list){
    const o=document.createElement("option");
    o.value=String(a.alias);
    o.textContent=String(a.alias)+(a.title?("（"+a.title+"）"):"")+(a.pendingMail?(" · 信箱 "+a.pendingMail):"");
    sel.appendChild(o);
  }
  if(keep)sel.value=keep;
}
function taskAccRow(v){
  const wrap=document.createElement("div");
  wrap.className="tp-acc";
  const inp=document.createElement("input");
  inp.className="tp-acc-in";
  inp.placeholder="一条能判定的标准，例如「selftest 全绿」";
  inp.value=String(v||"");
  const del=document.createElement("button");
  del.type="button";del.className="tp-del";del.textContent="✕";del.title="删掉这条";
  del.addEventListener("click",()=>{
    if($("#taskAcc").querySelectorAll(".tp-acc").length<=1){inp.value="";return;}
    wrap.remove();
  });
  wrap.appendChild(inp);wrap.appendChild(del);
  return wrap;
}
function taskAccAdd(v){$("#taskAcc").appendChild(taskAccRow(v));}
function openTaskPage(){
  $("#taskPage").classList.add("on");
  $("#taskResult").innerHTML="";
  $("#taskTitle").value="";$("#taskGoal").value="";$("#taskDue").value="";
  $("#taskAcc").innerHTML="";
  taskAccAdd("");
  taskRenderAssignees();
  if(TASK_META)taskMetaApply(TASK_META);
  fetchT("/api/meta",{},8000).then(r=>r.json()).then(taskMetaApply).catch(()=>{});
  setTimeout(()=>{try{$("#taskTitle").focus();}catch(e){}},50);
}
function closeTaskPage(){$("#taskPage").classList.remove("on");}
function taskResultShow(kind,html){
  const box=$("#taskResult");
  if(!box)return;
  box.innerHTML="";
  const d=document.createElement("div");
  d.className="tp-res "+kind;
  d.innerHTML=html;
  box.appendChild(d);
}
async function submitTask(){
  const assignee=String($("#taskAssignee").value||"").trim();
  const title=String($("#taskTitle").value||"").trim();
  const goal=String($("#taskGoal").value||"").trim();
  const due=String($("#taskDue").value||"").trim();
  const acc=[].slice.call($("#taskAcc").querySelectorAll(".tp-acc-in"))
    .map(e=>String(e.value||"").trim()).filter(Boolean);
  const kind=String($("#taskKind").value||"dev"), prio=String($("#taskPrio").value||"P2"), prefix=String($("#taskPrefix").value||"HUB");
  if(!assignee){toast("先选派给谁");return;}
  if(title.length<4){toast("标题至少 4 个字");return;}
  if(!acc.length){toast("没有验收标准不许派（至少一条）");return;}
  const btn=$("#taskSubmit");
  btn.disabled=true;
  try{
    const r=await fetchT("/api/tasks",{method:"POST",headers:{"Content-Type":"application/json","x-mchat-token":token},
      body:JSON.stringify({author:"老板",assignee:assignee,title:title,goal:goal,acceptance:acc,kind:kind,priority:prio,prefix:prefix,due:due})},20000);
    const j=await r.json();
    if(!r.ok){taskResultShow("warn","派单没成："+String(j.error||r.status));toast("派单失败");return;}
    const dv=j.delivery||{};
    const cls=dv.status==="woken"?"ok":(dv.status==="not-woken"?"warn":"info");
    const icon=dv.status==="woken"?"✅":(dv.status==="not-woken"?"⚠️":"📥");
    taskResultShow(cls,"<span class='tp-id'>"+String(j.id)+"</span> · "+icon+" "+String(dv.text||"已提交")+
      "<span class='tp-sub'>卡：docs/tasks/"+String(j.id)+".md ｜ 接手：@"+assignee+"</span>");
    toast("已派 "+String(j.id));
    load();
  }catch(e){taskResultShow("warn","派单失败：网络/超时（卡可能没落，别重复点）");}
  finally{btn.disabled=false;}
}
function renderContacts(q){
  const box=$("#contactsList");
  if(!box)return;
  box.innerHTML="";
  const key=String(q||"").trim().toLowerCase();
  const list=(AGENTS||[]).slice().sort((a,b)=>String(a.alias).localeCompare(String(b.alias)));
  const hits=list.filter((a)=>{
    if(!key)return true;
    return (String(a.alias)+" "+String(a.title||"")+" "+String(a.note||"")).toLowerCase().indexOf(key)>=0;
  });
  if(!hits.length){
    const e=document.createElement("div");
    e.className="sempty";
    e.textContent="没有匹配的线";
    box.appendChild(e);
    return;
  }
  for(const a of hits){
    const row=document.createElement("div");
    row.className="ct";
    row.dataset.alias=a.alias;
    row.appendChild(avNode(a.alias,"lg"));
    const main=document.createElement("div");
    main.className="ct-main";
    const nm=document.createElement("div");
    nm.className="ct-name";
    const b=document.createElement("b");
    b.textContent=a.alias;
    nm.appendChild(b);
    if(a.duty){const t=document.createElement("span");t.className="tag";t.textContent="值守";nm.appendChild(t);}
    const sub=document.createElement("div");
    sub.className="ct-sub";
    sub.textContent=[a.title||"",a.note||""].filter(Boolean).join(" · ")||"（未填职责）";
    main.appendChild(nm);main.appendChild(sub);
    row.appendChild(main);
    const right=document.createElement("div");
    right.className="ct-right";
    const bits=[];
    if(a.pendingMail>0)bits.push('<span class="ct-badge">'+a.pendingMail+'</span>');
    if(a.open>0)bits.push("待办 "+a.open);
    bits.push(a.retired?"退役":a.status==="active"?"在岗":a.status==="idle"?"闲":a.status==="stale"?"久未动静":"未上岗");
    right.innerHTML=bits.join("<br>");
    row.appendChild(right);
    row.addEventListener("click",()=>{
      setTarget(a.alias);
      closeContacts();
      toast("收件人已切到 "+a.alias);
      try{msgEl.focus();}catch(e){}
    });
    box.appendChild(row);
  }
}
function searchHits(q){
  const key=String(q||"").trim().toLowerCase();
  // 任务改号后：正文字段已经是新号，所以搜旧号要能命中 -> 用别名表把关键字也换算一遍（双向可查）
  let key2=key;
  for(const k in TASK_ALIAS){ const lk=String(k).toLowerCase(); if(key2.indexOf(lk)>=0)key2=key2.split(lk).join(String(TASK_ALIAS[k]).toLowerCase()); }
  const list=(CACHE||[]).filter((r)=>r.kind!=="progress");
  if(!key)return list.slice(-40).reverse();
  return list.filter((r)=>{
    const refs=r.refs||{};
    const hay=(String(r.from||"")+" "+String(r.to||"")+" "+String(r.body||"")+" "+
      String(refs.inbox||"")+" "+String(refs.bridge||"")+" "+String(refs.bridgeTask||"")+" "+String(r.channel||"")).toLowerCase();
    return hay.indexOf(key)>=0 || (key2!==key && hay.indexOf(key2)>=0);
  }).slice(-80).reverse();
}
function renderSearch(q){
  const box=$("#searchResults");
  const hits=searchHits(q);
  box.innerHTML="";
  if(!hits.length){
    const e=document.createElement("div");
    e.className="sempty";
    e.textContent=String(q||"").trim()?"没有匹配的记录":"输入关键词搜索（内容 / 实例名 / 任务文件名）";
    box.appendChild(e);
    return;
  }
  const key=String(q||"").trim();
  for(const r of hits){
    const row=document.createElement("div");
    row.className="sres";
    const n=document.createElement("div");
    n.className="n";
    n.textContent=r.from+" → "+r.to;
    const t=document.createElement("div");
    t.className="t";
    t.textContent=String(r.ts||"").slice(5,16).replace("T"," ")+" · "+r.channel+"/"+r.kind;
    const b=document.createElement("div");
    b.className="b";
    const body=String(r.body||"").replace(/\\s+/g," ");
    if(key){
      // 命中高亮也要认别名：搜旧号时正文里是新号，得换算后再找位置
      let kl=key.toLowerCase();
      let i=body.toLowerCase().indexOf(kl);
      if(i<0){ for(const a in TASK_ALIAS){ const lk=String(a).toLowerCase(); if(kl.indexOf(lk)>=0)kl=kl.split(lk).join(String(TASK_ALIAS[a]).toLowerCase()); } i=body.toLowerCase().indexOf(kl); }
      if(i>=0){
        b.appendChild(document.createTextNode(body.slice(Math.max(0,i-18),i)));
        const em=document.createElement("em");
        em.textContent=body.slice(i,i+kl.length);
        b.appendChild(em);
        b.appendChild(document.createTextNode(body.slice(i+kl.length,i+kl.length+40)));
      }else b.textContent=body.slice(0,60);
    }else b.textContent=body.slice(0,60);
    row.appendChild(n);row.appendChild(t);row.appendChild(b);
    row.addEventListener("click",()=>jumpToRecord(r.id));
    box.appendChild(row);
  }
}
function jumpToRecord(id){
  closeSearch();
  let el=boardEl.querySelector('[data-id="'+id+'"]');
  if(!el){ // 被筛选挡住了就先放开筛选再找
    FILTER.mode="all";
    FILTER.alias=null;
    renderDialog(CACHE);
    syncTools();
    el=boardEl.querySelector('[data-id="'+id+'"]');
  }
  if(!el)return;
  el.scrollIntoView({block:"center"});
  el.classList.add("flash");
  setTimeout(()=>el.classList.remove("flash"),1600);
}
// —— 右下角：回到底部 + 新消息扁条 ——
function atBottom(){return boardEl.scrollHeight-boardEl.scrollTop-boardEl.clientHeight<60;}
function updateJump(){
  $("#jump").classList.toggle("on",!atBottom());
}
function jumpToBottom(){
  boardEl.scrollTop=boardEl.scrollHeight;
  hideNewPill();
  updateJump();
}
function showNewPill(text){
  $("#newPillText").textContent=text||"有新消息";
  $("#newPill").classList.add("on");
}
function hideNewPill(){$("#newPill").classList.remove("on");}
// 输入框自适应高度（1~5 行），不占死空间
function autoGrow(){
  msgEl.style.height="auto";
  msgEl.style.height=Math.min(msgEl.scrollHeight,120)+"px";
}
// 诊断行：手机上看不到控制台，这行就是"病历"——记录数 / 渲染行数 / 当前筛选 / 出错原因
let LAST_RENDERED=0, LAST_RECORDS=0;
// 把"我现在渲染成什么样"报回服务端：我看不到屏幕时，就去读 outputs/dialog/ui_report.json
function uiReport(extra){
  try{
    const wrap=$("#boardWrap");
    const payload={
      ver:PAGE_VER,
      w:window.innerWidth||0,
      h:window.innerHeight||0,
      records:LAST_RECORDS,
      rendered:LAST_RENDERED,
      mode:FILTER.mode,
      alias:FILTER.alias||"",
      boardH:(boardEl&&boardEl.clientHeight)||0,
      boardScrollH:(boardEl&&boardEl.scrollHeight)||0,
      wrapH:(wrap&&wrap.clientHeight)||0,
      boardChildren:(boardEl&&boardEl.children)?boardEl.children.length:0,
      hasToken:!!token,
    };
    if(extra)Object.assign(payload,extra);
    fetchT("/api/uireport",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)},8000).catch(function(){});
  }catch(e){}
}
function setDiag(extra, warn){
  const d=$("#diag");
  if(!d)return;
  d.textContent="v"+PAGE_VER.split(".").pop()+" · 记录 "+LAST_RECORDS+" · 显示 "+LAST_RENDERED+" 行 · "+
    (FILTER.mode==="all"?"全部":FILTER.mode==="todo"?"待办":FILTER.mode==="unread"?"未读":"公告")+(FILTER.alias?"/"+FILTER.alias:"")+
    (HIDDEN_PROG?" · 进度已折叠 "+HIDDEN_PROG:"")+(HIDDEN_OLD_NOTICE?" · 已过期/被取代公告 "+HIDDEN_OLD_NOTICE+" 条已收起":"")+(extra?" · "+extra:"");
  d.style.color=warn?"#f0b847":"var(--dim)";
}
let token=localStorage.getItem("mchat_token")||new URLSearchParams(location.search).get("t")||"";
if(token)localStorage.setItem("mchat_token",token);
function askToken(){
  const t=prompt("请输入访问口令：");
  if(t){token=t.trim();localStorage.setItem("mchat_token",token);}
}
// 提及前缀是服务端的路由真值（消息以 @名字 开头时以该名字为收件人）。
// 界面上必须跟着它走，否则老板看到的目标会和实际收件人不一致。
function mentionPrefixOf(text){
  const m=String(text||"").match(/^\\s*@([A-Za-z0-9_\\u4e00-\\u9fa5-]{1,32})/);
  return m?m[1]:null;
}
// 收件人清单来自实例注册表（agents.json），不再写死三个名字；
// 没写 @前缀时才用这里选中的兜底收件人。
let TARGET=localStorage.getItem("mchat_target")||"codex-看板服务";
let AGENTS=[];
// 旧句柄存下来的选择自动升级到看板名（真源 docs/BOARD_NAMES.md）
const TARGET_ALIAS={"codex":"codex-看板服务","dsh":"dsh-老员工","dsh-main":"dsh-老员工","codex-convtool":"codex-看板编辑","codex-dsh唤醒":"codex-唤醒通道"};
TARGET=TARGET_ALIAS[String(TARGET).toLowerCase()]||TARGET;
function knownTargets(){
  const list=[];
  for(const a of (AGENTS||[])){
    const al=String(a&&a.alias||"");
    if(al&&list.indexOf(al)<0)list.push(al);
  }
  if(list.indexOf("codex-看板服务")<0)list.unshift("codex-看板服务");
  if(list.indexOf("老板")<0)list.push("老板");
  if(list.indexOf("全体")<0)list.push("全体"); // 公告：所有人可见、谁都不回
  return list;
}
function effectiveTarget(){
  return mentionPrefixOf(msgEl.value)||TARGET;
}
function renderTargets(){
  const sel=$("#targetSel");
  if(!sel)return;
  const list=knownTargets();
  if(TARGET&&list.indexOf(TARGET)<0)list.push(TARGET);
  const key=list.join(",");
  if(sel.dataset&&sel.dataset.list===key)return;
  if(sel.dataset)sel.dataset.list=key;
  sel.innerHTML="";
  for(const t of list){
    const o=document.createElement("option");
    o.value=t;
    o.textContent=(t==="全体")?"@全体（公告·不回复）":("@"+t);
    if(t===TARGET)o.selected=true;
    sel.appendChild(o);
  }
}
function setTarget(t){
  TARGET=String(t||"codex-看板服务");
  try{localStorage.setItem("mchat_target",TARGET);}catch(e){}
  const sel=$("#targetSel");
  if(sel)sel.value=TARGET;
  refreshRouteHint();
}
function insertMention(alias){
  const a=String(alias||"").trim();
  if(!a)return;
  const cur=msgEl.value;
  const sep=cur&&!/\\s$/.test(cur)?" ":"";
  msgEl.value=(cur+sep+"@"+a+" ").replace(/^\\s+/,"");
  msgEl.focus();
  statusEl.textContent="已插入 @"+a;
  refreshRouteHint();
  toast("已 @ 提及 "+a+"（前缀决定收件人）");
}
// 长按触发后会紧跟一次 click（触摸与鼠标都会），用时间戳把那次 click 吃掉，
// 否则实例胶囊会「又插了提及又切了筛选」。
let lpFiredAt=0;
function lpSuppressClick(){
  return !!lpFiredAt&&Date.now()-lpFiredAt<800;
}
function addLongPress(el,fn){
  let timer=null;
  const start=()=>{ if(timer)return; timer=setTimeout(()=>{timer=null;lpFiredAt=Date.now();fn();},450); };
  const cancel=()=>{ if(timer){clearTimeout(timer);timer=null;} };
  el.addEventListener("touchstart",start,{passive:true});
  el.addEventListener("touchmove",cancel,{passive:true});
  el.addEventListener("touchend",cancel);
  el.addEventListener("touchcancel",cancel);
  el.addEventListener("contextmenu",(e)=>{e.preventDefault();cancel();fn();});
  el.addEventListener("mousedown",start);
  el.addEventListener("mouseup",cancel);
  el.addEventListener("mouseleave",cancel);
}
function refreshRouteHint(){
  const el=$("#routeHint"),sel=$("#targetSel");
  const pre=mentionPrefixOf(msgEl.value);
  if(sel)sel.classList.toggle("overridden",!!pre);
  if(pre==="全体"||(!pre&&effectiveTarget()==="全体")){
    if(el){
      el.textContent="→ 公告：所有线都会看到，但谁都不会回复（也不会唤醒任何人）";
      el.style.display="block";
    }
    return;
  }
  if(pre){
    if(el){
      el.textContent="→ 按前缀发给 @"+pre+"（@前缀优先，左边选的 "+"@"+TARGET+" 这次不生效）";
      el.style.display="block";
    }
    return;
  }
  if(QUOTE){
    if(el){
      el.textContent="→ 引用回复，发给 @"+TARGET+"（引用头不改路由；要换人就在开头写 @名字）";
      el.style.display="block";
    }
    return;
  }
  if(el){
    el.textContent="";
    el.style.display="none";
  }
}
function nameClass(author){
  const a=String(author||"").toLowerCase();
  if(a.startsWith("codex"))return "codex";
  if(a==="老板"||a==="boss")return "boss";
  if(a.startsWith("dsh"))return "dsh";
  return "other";
}
const FILTER={mode:"all",alias:null,q:"",group:null};
// 任务改号别名表（服务端 /api/ping 下发；用于搜索时把旧号换算成新号，双向可查）
let TASK_ALIAS={};
let SEEN=new Set();
try{SEEN=new Set(JSON.parse(localStorage.getItem("mchat_seen")||"[]"));}catch(e){SEEN=new Set();}
// HUB-011：本设备的稳定 id（把"看到哪儿"报给服务端；将来 App/多端可共享同一份已读状态）
let DEVICE_ID=(function(){try{let d=localStorage.getItem("mchat_dev");if(!d){d="dev-"+Math.random().toString(36).slice(2,10);localStorage.setItem("mchat_dev",d);}return d;}catch(e){return "dev-anon";}})();
let CACHE=[],CACHE_VIOL=[],CACHE_ADDED=[],QUOTE=null,UNREAD_N=0,firstLoad=true,NOTIFY=localStorage.getItem("mchat_notify")==="1";
// dsh 的进度流是英文思考（reasoning…），默认**不显示**，免得糊满聊天框；
// 需要看的时候在 ⋯ 菜单里打开。
let SHOW_PROGRESS=localStorage.getItem("mchat_prog")==="1";
let HIDDEN_PROG=0;
let HIDDEN_OLD_NOTICE=0; // 公告页签里被收起来的"已过期/已被取代"条数
function saveSeen(){
  try{localStorage.setItem("mchat_seen",JSON.stringify([...SEEN].slice(-800)));}catch(e){}
  // HUB-011：顺手把游标报给服务端（多设备同步的地基；失败不影响任何本地行为）
  try{
    const newest=(typeof SEEN!=="undefined"&&SEEN.size)?[...SEEN].slice(-1)[0]:"";
    if(newest&&token)fetchT("/api/read",{method:"POST",headers:{"Content-Type":"application/json","x-mchat-token":token},
      body:JSON.stringify({deviceId:DEVICE_ID,upToId:newest})},8000).catch(function(){});
  }catch(e){}
}
function isTodo(r){
  return !!(r&&(r.overdue||r.state==="open"||r.state==="dispatched"||r.state==="待办"));
}
function pass(r){
  if(FILTER.mode==="notice")return r.kind==="notice"; // 公告页签：只看公告（连它的回执一起看）
  if(FILTER.mode==="todo"&&!isTodo(r))return false;
  if(FILTER.mode==="unread"&&SEEN.has(r.id))return false;
  if(FILTER.alias&&String(r.to||"").toLowerCase()!==FILTER.alias)return false;
  // 群组筛选（HUB-010）：消息里的收发方只要落在群成员里，或显式标了 refs.group
  if(FILTER.group){
    const g=(GROUPS||[]).find(x=>x.id===FILTER.group);
    if(g){
      const mem=new Set((g.members||[]).map(x=>String(x).toLowerCase()));
      const f=String(r.from||"").toLowerCase(),t=String(r.to||"").toLowerCase();
      const rg=String((r.refs&&r.refs.group)||"");
      if(rg!==g.id&&!mem.has(f)&&!mem.has(t))return false;
    }
  }
  if(FILTER.q){
    const refs=r.refs||{};
    const hay=(String(r.from||"")+" "+String(r.to||"")+" "+String(r.body||"")+" "+
      String(refs.inbox||"")+" "+String(refs.bridge||"")+" "+String(refs.bridgeTask||"")+" "+String(r.channel||"")).toLowerCase();
    if(hay.indexOf(FILTER.q)<0)return false;
  }
  return true;
}
function countTodo(records){
  return (records||[]).filter(r=>r.kind!=="progress"&&isTodo(r)).length;
}

// —— HUB-003 置顶「待老板：N 条」——
// 只推三类事件（待验收/需拍板/故障），每条都必须带"要你做什么"；
// 页面内提醒**只在你开着本页面时有效**——这句话必须出现在界面上，不许含糊成"已通知你"。
let BOSS={count:0,muted:false,items:[],note:""};let BOSS_SEEN_N=null;
// —— HUB-006 暂停闸条 ——
// 暂停中：红条「已暂停 · 等老板」+ 原因；恢复后 6 小时内显示绿条「已恢复 · 老板 <时间>」。
// 这一条比推送可靠：**不依赖任何通道**，打开页面就一定看到。
function haltRender(h){
  const el=$("#haltBar");
  if(!el)return;
  const H=h||{};
  if(H.halted){
    el.className="halt";
    el.innerHTML="";
    const b=document.createElement("b");
    b.textContent="已暂停 · 等老板";
    const g=document.createElement("div");
    g.className="grow2";
    g.textContent=(H.severity?H.severity+" ":"")+String(H.reason||"");
    el.appendChild(b);el.appendChild(g);
    return;
  }
  const at=H.resumedAt?Date.parse(String(H.resumedAt)):0;
  if(at&&Date.now()-at<6*3600*1000){
    el.className="resumed";
    el.innerHTML="";
    const b=document.createElement("b");
    b.textContent="已恢复";
    const g=document.createElement("div");
    g.className="grow2";
    g.textContent="老板 "+String(H.resumedAt||"").slice(11,16)+" 解除暂停";
    el.appendChild(b);el.appendChild(g);
    return;
  }
  el.className="off";
  el.innerHTML="";
}
function bossRender(){
  const bar=$("#bossBar"),list=$("#bossList");
  if(!bar)return;
  const n=Number(BOSS.count||0);
  if(!n){bar.className="off";list.className="";list.innerHTML="";return;}
  const top=(BOSS.items||[])[BOSS.items.length-1]||{};
  bar.className=BOSS.muted?"muted":"";
  bar.innerHTML="";
  const b=document.createElement("b");
  b.textContent=(BOSS.muted?"（提醒已静音）":"🔔 ")+"待老板："+n+" 条";
  const g=document.createElement("div");
  g.className="grow";
  g.textContent=(top.kindLabel?("["+top.kindLabel+"] "):"")+String(top.needAction||"");
  const det=document.createElement("button");
  det.textContent="详情";
  det.addEventListener("click",()=>{list.className=list.className==="on"?"":"on";});
  const mu=document.createElement("button");
  mu.textContent=BOSS.muted?"恢复提醒":"静音";
  mu.addEventListener("click",async()=>{
    try{
      await fetchT("/api/boss-mute",{method:"POST",headers:{"Content-Type":"application/json","x-mchat-token":token},body:JSON.stringify({on:!BOSS.muted})},10000);
      BOSS.muted=!BOSS.muted;bossRender();load();
    }catch(e){}
  });
  bar.appendChild(b);bar.appendChild(g);bar.appendChild(det);bar.appendChild(mu);
  list.innerHTML="";
  const note=document.createElement("div");
  note.className="row";
  note.textContent="（"+String(BOSS.note||"页面内提醒只在你开着本页面时有效")+"）";
  list.appendChild(note);
  for(const it of (BOSS.items||[]).slice().reverse()){
    const r=document.createElement("div");
    r.className="row";
    const k=document.createElement("div");
    k.className="k";
    k.textContent="["+(it.kindLabel||it.kind)+"] "+(it.task?it.task+" · ":"")+String(it.from||"")+" · "+String(it.ts||"").slice(5,16).replace("T"," ");
    const a=document.createElement("div");
    a.textContent="要你做什么："+String(it.needAction||"");
    r.appendChild(k);r.appendChild(a);list.appendChild(r);
  }
  // 新事件才提醒一次：标题闪烁（页面开着才看得到——见上面的说明）
  if(BOSS_SEEN_N===null)BOSS_SEEN_N=n;
  else if(n>BOSS_SEEN_N&&!BOSS.muted){
    const base=document.title;
    let i=0,on=false;
    const t=setInterval(()=>{document.title=(on?"🔔 ":"")+base;on=!on;if(++i>=8){clearInterval(t);document.title=base;}},600);
  }
  BOSS_SEEN_N=n;
}
function countNotice(records){
  return (records||[]).filter(r=>r.kind==="notice").length;
}
// （已删除 2026-09-12 00:3x：unreadCount() —— 与 UNREAD_N 重复，零调用点）
function syncTools(){
  for(const b of document.querySelectorAll("#modes button"))b.classList.toggle("on",b.dataset.mode===FILTER.mode);
  const t=$("#todoN"),u=$("#unreadN");
  if(t)t.textContent=countTodo(CACHE)?"("+countTodo(CACHE)+")":"";
  if(u)u.textContent=UNREAD_N?"("+UNREAD_N+")":"";
  const nn=$("#noticeN");
  if(nn)nn.textContent=countNotice(CACHE)?"("+countNotice(CACHE)+")":"";
  const a=$("#agents");
  if(a)for(const c of a.children)c.classList.toggle("sel",!!FILTER.alias&&c.dataset.alias===FILTER.alias);
  // 面板收起时，用标题栏那行小字交代"有几个实例 / 多少待办"，不用展开也知道
  if(summaryEl){
    summaryEl.textContent=panelOpen?"":(AGENTS.length+" 实例 · 待办 "+countTodo(CACHE)+(UNREAD_N?" · 未读 "+UNREAD_N:""));
  }
}
function renderAgents(list){
  agentsEl.innerHTML="";
  for(const a of (list||[])){
    const chip=document.createElement("span");
    chip.className="chip"+(a.open>0?" open":"")+(a.status==="active"?" online":"");
    chip.dataset.alias=a.alias;
    chip.title="点一下只看发给 "+a.alias+" 的记录；长按插入 @"+a.alias+(a.auto?"（自动登记的成员，待补 title/slug）":"");
    chip.addEventListener("click",()=>{
      if(lpSuppressClick())return;
      FILTER.alias=FILTER.alias===a.alias?null:a.alias;
      renderDialog(CACHE);
      syncTools();
    });
    // 头像 + 状态色环（原来那个纯色圆点保留成"环"的信息量，但更好看）
    const dot=avNode(a.alias,"sm");
    dot.style.boxShadow="0 0 0 2px "+(a.status==="active"?"#3fb950":a.status==="idle"?"#d29922":a.status==="stale"?"#6e7681":"#484f58");
    const nm=document.createElement("b");
    nm.textContent=a.alias;
    const st=document.createElement("span");
    // 「待办 N · 信箱 M」：信箱数 = 压在它信箱里还没被处理的留言（拉模式可见化，HUB-005）
    const bits=[];
    if(a.open>0)bits.push("待办 "+a.open);
    if(a.pendingMail>0)bits.push("信箱 "+a.pendingMail);
    st.textContent=bits.length?bits.join(" · "):healthText(a);
    if(a.pendingMail>0)st.classList.add("mail");
    if(a.retired)chip.classList.add("retired");
    chip.appendChild(dot);chip.appendChild(nm);chip.appendChild(st);
    addLongPress(chip,()=>insertMention(a.alias));
    agentsEl.appendChild(chip);
  }
}
// 状态自动维护：芯片文字用“多久前活动过”，不靠人维护 status 字段
function healthText(a){
  if(a.retired)return "退役";           // HUB-013：退役的线**灰显「退役」**，不消失（可追溯）
  const m=a.idleMin;
  if(m==null)return a.auto?"自动发现":"未见过";
  if(m<60)return m+" 分钟前";
  if(m<1440)return Math.round(m/60)+" 小时前";
  return Math.round(m/1440)+" 天前";
}
// 署名规约审计：谁没按「前缀-短名」写，摆到台面上，不再静默归一。
// 但必须“吵一次就够”：✕ 之后记下已确认的最大时间戳，同样的旧账不再出现（新的违规才再弹）。
function violAck(){try{return localStorage.getItem("mchat_viol_ack")||"";}catch(e){return "";}}
function freshViolations(list){const ack=violAck();return (list||[]).filter((v)=>String(v.lastTs||"")>ack);}
let LAST_VIOL_TS="";
function renderWarn(violations,added){
  const el=$("#warn"),txt=$("#warnText");
  const fresh=freshViolations(violations);
  LAST_VIOL_TS=fresh.reduce((m,v)=>String(v.lastTs||"")>m?String(v.lastTs||""):m,"");
  const parts=[];
  if(added&&added.length)parts.push("新成员已自动登记："+added.join("、")+"（状态栏已出现）");
  for(const v of fresh.slice(0,3))parts.push("署名未按规约：「"+v.raw+"」×"+v.count+" → 已归一为 "+v.mapped);
  if(fresh.length>3)parts.push("另有 "+(fresh.length-3)+" 种");
  if(!parts.length){el.classList.remove("on");txt.textContent="";return;}
  txt.textContent="⚠ "+parts.join("；")+"（点 ✕ 之后同样的旧账不再提示）";
  el.classList.add("on");
}
// 消息正文渲染：把三反引号围栏里的代码块、行内反引号代码从纯文字里分出来（参考 Codex 自己的聊天）
// 注意：这一段在模板字符串里，所有反引号都要写成 \` ，换行转义要写成 \\n 。
// 保守的"英文标识符"识别：路径 / 文件名 / --flag / hex / 版本号 / snake_case / camelCase。
// **宁可少套**：只在 ASCII 单词边界上命中，绝不切开中文句子。
const MONO_RE=new RegExp(
  "([A-Za-z]:\\\\\\\\[^\\\\s，。；、（）]+" +
  "|/(?:mnt|home|usr|var|opt|tmp|e)/[^\\\\s，。；、（）]+" +
  "|--[A-Za-z][A-Za-z0-9-]*" +
  "|[A-Za-z0-9_.-]+\\\\.(?:py|md|mjs|js|cjs|json|exe|ps1|bat|cmd|log|txt|ndjson|toml|ya?ml|csv|ts|tsx|sqlite)" +
  "|0x[0-9A-Fa-f]{4,}" +
  "|v?\\\\d+\\\\.\\\\d+(?:\\\\.\\\\d+)*" +
  "|[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+" +
  "|[a-z][a-z0-9]*(?:[A-Z][A-Za-z0-9]+)+)",
  "g"
);
function monoSplit(s){
  const out=[];
  let last=0;
  MONO_RE.lastIndex=0;
  let m;
  while((m=MONO_RE.exec(s))!==null){
    if(m.index>last)out.push({c:false,s:s.slice(last,m.index)});
    out.push({c:true,s:m[0]});
    last=m.index+m[0].length;
    if(m[0].length===0)MONO_RE.lastIndex++;
  }
  if(last<s.length)out.push({c:false,s:s.slice(last)});
  return out;
}
function renderBody(el, text){
  let src=String(text||"");
  // 行首标签（如〔代答〕〔承诺需本尊确认〕/〔已投递未唤醒〕）渲染成小圆角牌，别混在正文里当普通字看。
  // **可连挂多枚**（2026-09-11 22:5x：承诺类要在代答后面再挂一枚）。
  for(let guard=0;guard<4;guard++){
    const tag=src.match(/^〔([^〕]{1,16})〕\\s*/);
    if(!tag)break;
    const t=document.createElement("span");
    t.className="tag";
    t.textContent=tag[1];
    el.appendChild(t);
    src=src.slice(tag[0].length);
  }
  const FENCE="\`\`\`";
  const parts=src.split(FENCE);
  for(let i=0;i<parts.length;i++){
    const part=parts[i];
    if(i%2===1){
      const lines=part.replace(/^\\n+/,"").replace(/\\n+$/,"").split("\\n");
      let lang="";
      if(lines.length&&/^[A-Za-z0-9_+.-]{1,12}$/.test(String(lines[0]||"").trim()))lang=String(lines.shift()).trim();
      const pre=document.createElement("pre");
      pre.className="code";
      if(lang){
        const t=document.createElement("span");
        t.className="code-lang";
        t.textContent=lang;
        pre.appendChild(t);
      }
      const code=document.createElement("code");
      code.textContent=lines.join("\\n");
      pre.appendChild(code);
      el.appendChild(pre);
    }else{
      const BT="\`";
      const segs=part.split(new RegExp("("+BT+"[^"+BT+"\\\\n]+"+BT+")"));
      for(const s of segs){
        if(!s)continue;
        if(s.length>1&&s.charAt(0)===BT&&s.charAt(s.length-1)===BT){
          const c=document.createElement("code");
          c.className="ic";
          c.textContent=s.slice(1,-1);
          el.appendChild(c);
        }else{
          // 字体样式归一（老板 2026-09-11 07:5x）：**没写反引号**的英文标识符也自动呈等宽小块，
          // 这样新员工第一条纯文本发言也有格式。护栏：只改呈现、真源一字不动、**宁可少套**。
          for(const tk of monoSplit(s)){
            if(tk.c){
              const c=document.createElement("code");
              c.className="ic";
              c.textContent=tk.s;
              el.appendChild(c);
            }else{
              el.appendChild(document.createTextNode(tk.s));
            }
          }
        }
      }
    }
  }
}
// 派单/桥任务的细行文案（不占气泡，别跟对话抢注意力）
function taskLineText(r){
  const refs=r.refs||{};
  const inst=String(refs.instance||refs.claimedBy||r.to||"");
  const tag=r.channel==="bridge"?"桥":"派单";
  let st="待回";
  if(r.overdue)st="待办";
  else if(r.state==="done")st="已完成";
  else if(r.state==="failed")st="失败";
  // 不再把任务正文（里面全是文件路径、会话 id、inbox 文件名这类英文）摊在聊天流里，
  // 只看"派给谁 / 什么状态"；正文留在 title（桌面悬停可见）与 Hub 记录里备查。
  return {tag:tag,text:"→ "+inst+" · "+st};
}
function stateText(r){
  if(r.overdue)return "待办 "+Math.round((Date.now()-Date.parse(r.ts))/60000)+" 分";
  const s=r.state||"";
  if(s==="dispatched")return r.kind+" · 已派单待回";
  if(s==="open")return r.kind+" · 待处理";
  if(s==="done")return r.kind+" · 已完成";
  if(s==="failed")return r.kind+" · 失败";
  return s?r.kind+" · "+s:r.kind;
}
function renderDialog(records){
  boardEl.innerHTML="";
  HIDDEN_PROG=0;
  HIDDEN_OLD_NOTICE=0;
  const shown=(records||[]).filter(pass);
  LAST_RENDERED=shown.length;
  if(!shown.length){
    const e=document.createElement("div");
    e.className="empty";
    // 空列表必须说清"为什么空"，否则看起来就是"啥也没有"
    e.textContent=(FILTER.mode==="notice")
      ? "还没有公告（发公告：收件人下拉选「@全体（公告·不回复）」）"
      : (records&&records.length)
      ? "没有符合当前筛选的记录（共 "+(records.length-((records||[]).filter(r=>r.kind==="progress").length))+" 条对话，当前筛选："+
        (FILTER.mode==="all"?"全部":FILTER.mode==="todo"?"待办":FILTER.mode==="unread"?"未读":"公告")+(FILTER.alias?" · 只看 "+FILTER.alias:"")+
        (FILTER.group?(" · 群 "+String(((GROUPS||[]).find(x=>x.id===FILTER.group)||{}).name||"")):"")+"）"
      : "还没拉到任何记录（v"+PAGE_VER.split(".").pop()+"）——若是首次打开请刷新，或检查网络/口令";
    boardEl.appendChild(e);
    return;
  }
  let lastDay="";
  for(const r of shown){
    // 日期分隔条（聊天软件的惯例）：跨天时才出现，省得每条都念日期
    const day=String(r.ts||"").slice(5,10);
    if(day&&day!==lastDay){
      lastDay=day;
      const d=document.createElement("div");
      d.className="day";
      d.textContent=day.replace("-","月")+"日";
      boardEl.appendChild(d);
    }
    if(r.kind==="progress"){
      if(!SHOW_PROGRESS){HIDDEN_PROG++;continue;}
      const p=document.createElement("div");
      p.className="prog";
      const tag=document.createElement("span");
      tag.className="prog-tag";
      tag.textContent="进度";
      const t=document.createElement("span");
      t.className="prog-time";
      t.textContent=String(r.ts||"").slice(11,16);
      const b=document.createElement("span");
      b.className="prog-body";
      b.textContent=r.body||"";
      p.appendChild(tag);p.appendChild(t);p.appendChild(b);
      boardEl.appendChild(p);
      continue;
    }
    // 公告（@全体）：全宽卡片，一眼看出"这是公告，不用回"
    if(r.kind==="notice"){
      const refs=r.refs||{};
      // 公告页签默认只看"还生效的"：过期/被新公告取代的收起来（在"全部"里仍可查）
      if(FILTER.mode==="notice"&&!refs.active){HIDDEN_OLD_NOTICE++;continue;}
      const row=document.createElement("div");
      row.className="notice";
      row.dataset.id=r.id;
      const meta=document.createElement("div");
      meta.className="n-meta";
      const tag=document.createElement("span");
      tag.className="n-tag";
      tag.textContent="公告 "+noticeCode(r.id);   // 短号：回执就写「收到 N-xxxx」
      const who=document.createElement("span");
      who.textContent=(r.from||"")+" · "+String(r.ts||"").slice(5,16).replace("T"," ")+
        (refs.supersededBy?("　· 已被 "+String(refs.supersededBy).slice(11,16)+" 的公告取代"):"")+
        (refs.expired?"　· 已过期":"");
      meta.appendChild(tag);meta.appendChild(who);
      const bodyEl=document.createElement("div");
      bodyEl.className="n-body";
      if(!refs.active)bodyEl.style.opacity=".55";
      renderBody(bodyEl,r.body||"");
      bodyEl.addEventListener("click",()=>setQuote(r));
      row.appendChild(meta);row.appendChild(bodyEl);
      // 回执（钉钉式）：浅色小字 + 对号；未回执的也标出来，但**不谎报已读**
      const expected=refs.expected||[];
      if(expected.length&&refs.active){
        const ack=document.createElement("div");
        ack.className="n-ack";
        const acks=refs.acks||{};
        const okN=expected.filter(a=>acks[a]).length;
        const head=document.createElement("span");
        const allOk=okN===expected.length;
        head.textContent="已收到 "+okN+"/"+expected.length+(allOk?"（齐）":"（缺 "+String(expected.length-okN)+"）")+"：";
        head.title="回执写法：收到 "+noticeCode(r.id)+"（或引用这条公告回「收到」）";
        ack.appendChild(head);
        for(const a of expected){
          const tag=document.createElement("span");
          if(acks[a]){
            tag.className="ok";
            const m=acks[a].mode;
            tag.textContent="✓ "+a+" "+String(acks[a].ts).slice(5,16).replace("T"," ")+(m==="quote"?"（引用）":m==="code"?"（短号）":"（点名时间）");
            tag.title=m==="quote"?"引用回复这条公告":m==="code"?"回了短号":"按时间点名回执";
          }else{
            tag.className="no";
            tag.textContent="○ "+a+" 未收到";
          }
          ack.appendChild(tag);
        }
        row.appendChild(ack);
      }
      boardEl.appendChild(row);
      continue;
    }
    // 派单/桥任务：压成细行（原来是一条大气泡，和老板的原话几乎重复，最招人烦）
    if(r.kind==="task"&&(r.channel==="inbox"||r.channel==="bridge")){
      // 降噪（老板 2026-09-10 23:3x）：**对方及时回就不出现**。
      // 只有"没人接/超时（待办）"或"失败"才露一行；已派单待回、已完成都静默。
      // 记录本身仍留在 Hub 里（审计/待办筛选用），只是不占聊天流。
      if(!(r.overdue||r.state==="failed"))continue;
      const tl=taskLineText(r);
      const row=document.createElement("div");
      row.className="task-line"+(r.overdue?" s-todo":"");
      row.dataset.id=r.id;
      row.title=String(r.body||"").slice(0,300); // 正文（含路径/文件名）只在悬停时看，不进聊天流
      const tag=document.createElement("span");
      tag.className="tl-tag";
      tag.textContent=tl.tag;
      const bodyEl=document.createElement("span");
      bodyEl.className="tl-body";
      bodyEl.textContent=tl.text;
      row.appendChild(tag);row.appendChild(bodyEl);
      boardEl.appendChild(row);
      continue;
    }
    const cls=nameClass(r.from);
    const row=document.createElement("div");
    row.className="entry"+(cls==="boss"?" me":"");
    row.dataset.id=r.id;
    const meta=document.createElement("div");
    meta.className="meta";
    const name=document.createElement("span");
    name.className="name c-"+cls;
    name.textContent=r.from||"?";
    name.title="长按插入 @"+(r.from||"");
    addLongPress(name,()=>insertMention(r.from));
    if(cls!=="boss")meta.appendChild(avNode(r.from,"sm")); // 别人的消息带小头像（老板自己不带）
    const arrow=document.createElement("span");
    arrow.className="time";
    arrow.textContent="→ "+r.to;
    const time=document.createElement("span");
    time.className="time";
    time.textContent=String(r.ts||"").slice(5,16).replace("T"," ");
    if(r.channel&&r.channel!=="board"){
      const ch=document.createElement("span");
      ch.className="chan";
      ch.textContent=r.channel;
      meta.appendChild(name);meta.appendChild(arrow);meta.appendChild(time);meta.appendChild(ch);
    }else{
      meta.appendChild(name);meta.appendChild(arrow);meta.appendChild(time);
    }
    const kind=document.createElement("span");
    kind.className="state "+(r.overdue?"s-todo":r.state==="dispatched"?"s-dispatched":r.state==="done"?"s-done":"");
    kind.textContent=stateText(r);
    if(r.overdue||r.channel==="inbox"||r.channel==="bridge"){meta.appendChild(kind);}
    const qbtn=document.createElement("button");
    qbtn.className="qbtn";
    qbtn.textContent="↩ 引用";
    qbtn.title="引用这条记录回复";
    qbtn.addEventListener("click",()=>setQuote(r));
    meta.appendChild(qbtn);
    const bub=document.createElement("div");
    bub.className="bubble b-"+cls;
    renderBody(bub,r.body||""); // 代码块/行内代码单独成块，和纯文字区分开
    bub.addEventListener("click",()=>setQuote(r));
    row.appendChild(meta);
    if(r.refs&&r.refs.quote){
      const q=document.createElement("div");
      q.className="quote";
      q.textContent="↩ "+String(r.refs.quote.from||"")+" · "+String(r.refs.quote.ts||"").slice(5,16).replace("T"," ")+"："+String(r.refs.quote.body||"").slice(0,80);
      row.appendChild(q);
    }
    row.appendChild(bub);
    boardEl.appendChild(row);
  }
}
// （已删除 2026-09-12 00:3x：renderBoard() —— 早期"直接渲染看板原文"的路径，已被
//   renderDialog()（走 Hub 记录、带公告/引用/回执）完全取代，零调用点）
function nearBottom(){
  return boardEl.scrollHeight-boardEl.scrollTop-boardEl.clientHeight<100;
}
// 手机上很容易遇到“请求发出去了但永远不回”：切后台被挂起、Tailscale 抖动、服务重启。
// 没有超时的话按钮会永久停在“发送中…”，所以所有请求都带 AbortController 超时。
function fetchT(url,opts,ms){
  if(typeof AbortController!=="function")return fetch(url,opts);
  const ctl=new AbortController();
  const t=setTimeout(()=>ctl.abort(),ms);
  return fetch(url,Object.assign({},opts,{signal:ctl.signal})).finally(()=>clearTimeout(t));
}
let loading=false;
const PAGE_VER="${PAGE_VER}";
// 页面自己报错总得让人看见：出错就写到状态栏，别默默变成空白页
window.addEventListener("error",(e)=>{try{statusEl.textContent="页面出错："+(e.message||e.type||"");}catch(_){}});
window.addEventListener("unhandledrejection",(e)=>{try{statusEl.textContent="请求出错："+((e.reason&&e.reason.message)||e.reason||"");}catch(_){}});
function setQuote(r){
  QUOTE={id:r.id,from:r.from,ts:r.ts,body:r.body};
  const box=$("#quote");
  box.querySelector("span").textContent="↩ 回复 "+String(r.from||"")+" · "+String(r.ts||"").slice(5,16).replace("T"," ")+"："+String(r.body||"").slice(0,70);
  box.style.display="flex";
  // 引用谁就把兜底收件人调成谁（真名去注册表里找，找不到就不改；开头写 @名字 仍然优先）
  const want=knownTargets().filter(t=>t.toLowerCase()===String(r.from||"").toLowerCase())[0];
  if(want)setTarget(want);
  refreshRouteHint();
  msgEl.focus();
}
function clearQuote(){
  QUOTE=null;
  $("#quote").style.display="none";
  refreshRouteHint();
}
let toastTimer=null;
function toast(text){
  const el=$("#toast");
  el.textContent=text;
  el.style.display="block";
  if(toastTimer)clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>{el.style.display="none";},4000);
}
function syncNotifyBtn(){
  const b=$("#menuNotify");
  b.classList.toggle("on",NOTIFY);
  b.textContent="新消息提醒："+(NOTIFY?"开":"关");
}
function syncProgressBtn(){
  const b=$("#menuProgress");
  if(!b)return;
  b.classList.toggle("on",SHOW_PROGRESS);
  b.textContent="进度流："+(SHOW_PROGRESS?"开":"关");
}
function notifyNew(list){
  const fresh=list.filter(r=>r.kind!=="progress"&&String(r.from||"")!=="老板");
  if(!fresh.length)return;
  const top=fresh[fresh.length-1];
  const more=fresh.length>1?"（+"+(fresh.length-1)+"）":"";
  const text=String(top.from||"")+"："+String(top.body||"").slice(0,40)+more;
  toast(text);
  try{
    if(NOTIFY&&"Notification" in window&&Notification.permission==="granted"){
      new Notification("看板新消息",{body:text,tag:"mchat"});
    }
  }catch(e){}
}
async function load(){
  if(loading)return;
  loading=true;
  try{
    const [rb,rp]=await Promise.all([
      fetchT("/api/dialog?limit=200",{headers:{"x-mchat-token":token}},12000),
      fetchT("/api/ping",{headers:{"x-mchat-token":token}},12000)
    ]);
    if(rb.status===401||rp.status===401){askToken();return;}
    const j=await rb.json();
    const p=await rp.json();
    if(p.ver&&p.ver!==PAGE_VER){statusEl.textContent="页面已更新，正在刷新…";location.reload();return;}
    if(p.aliases)TASK_ALIAS=p.aliases;
    AVATARS={};
    for(const a of (j.agents||[])) if(a.avatar)AVATARS[a.alias]=a.avatar;
    if(j.boss){BOSS=j.boss;bossRender();}
    if(j.halt)haltRender(j.halt);
    GROUPS=j.groups||[];
    renderGroups();
    const records=j.records||[];
    CACHE=records;
    LAST_RECORDS=records.length;
    AGENTS=j.agents||[];
    renderTargets();
    refreshRouteHint();
    const unread=records.filter(r=>!SEEN.has(r.id));
    UNREAD_N=unread.length;
    renderAgents(j.agents);
    CACHE_VIOL=j.nameViolations||[];
    CACHE_ADDED=j.addedMembers||[];
    renderWarn(CACHE_VIOL,CACHE_ADDED);
    syncTools();
    const stick=nearBottom();
    renderDialog(records);
    if(stick){suppressAutoUntil=Date.now()+800;boardEl.scrollTop=boardEl.scrollHeight;}
    const shown=records.filter(pass);
    for(const r of shown)SEEN.add(r.id);
    saveSeen();
    document.title=(UNREAD_N?"("+UNREAD_N+") ":"")+"团队共享看板";
    if(!firstLoad)notifyNew(unread.filter(r=>Date.now()-Date.parse(r.ts)<10*60*1000));
    // 老板在翻旧消息（不在底部）时有新东西进来 → 右下角一条扁扁的新消息提示，点一下到底
    if(!firstLoad&&!atBottom()){
      const fresh=unread.filter(r=>r.kind!=="progress");
      if(fresh.length){
        const last=fresh[fresh.length-1];
        // 注意：这一段在模板字符串里，反斜杠加 n 会被 Node 变成真换行，页面脚本就会语法错；
        // 所以下面 split 的参数必须写成双反斜杠加 n（渲染出去才是真正的换行转义）。
        const line=String(last.body||"").split("\\n")[0];
        showNewPill((fresh.length>1?fresh.length+" 条新消息 · ":"")+line);
      }
    }
    updateJump();
    firstLoad=false;
    statusEl.textContent=p.busy?"Codex 回复中…":"已同步 "+(j.updatedAt||"")+" · v"+PAGE_VER.split(".").pop();
    const violFresh=freshViolations(CACHE_VIOL).length;
    setDiag((p.busy?"Codex 回复中":"正常")+(violFresh?" · 署名违规 "+violFresh:""));
    uiReport({ok:true,status:statusEl.textContent});
  }catch(e){
    statusEl.textContent=(e&&e.name==="AbortError")?"请求超时，正在重试…":"连接失败";
    setDiag("拉取失败："+((e&&e.message)||e),true);
    uiReport({ok:false,error:String((e&&e.message)||e),status:statusEl.textContent});
  }finally{loading=false;}
}
sendEl.addEventListener("click",async()=>{
  const target=effectiveTarget();
  const message=msgEl.value.trim();
  if(!message)return;
  msgEl.value="";
  autoGrow();
  statusEl.textContent="发送中…";
  try{
    const body={target,message};
    if(QUOTE)body.quoteId=QUOTE.id;
    const r=await fetchT("/api/send",{method:"POST",headers:{"Content-Type":"application/json","x-mchat-token":token},body:JSON.stringify(body)},20000);
    const j=await r.json();
    if(r.status===401){askToken();return;}
    if(j.ok)clearQuote();
    statusEl.textContent=j.ok?"已发送，等待回复":"发送失败："+(j.error||"");
    if(j.ok)jumpToBottom();
    setTimeout(load,1200);
  }catch(e){
    loading=false;
    statusEl.textContent=(e&&e.name==="AbortError")
      ? "发送超时：已重新同步，看板上没出现就再发一次"
      : "发送失败：网络断了，重连后可重发";
    setTimeout(load,1500);
  }
});
$("#modes").addEventListener("click",(e)=>{
  const b=e.target.closest("button");
  if(!b)return;
  FILTER.mode=b.dataset.mode;
  renderDialog(CACHE);
  syncTools();
});
msgEl.addEventListener("input",refreshRouteHint);
msgEl.addEventListener("input",autoGrow);
$("#targetSel").addEventListener("change",(e)=>setTarget(e.target.value));
$("#quoteX").addEventListener("click",clearQuote);
$("#warnX").addEventListener("click",()=>{
  if(LAST_VIOL_TS){try{localStorage.setItem("mchat_viol_ack",LAST_VIOL_TS);}catch(e){}}
  renderWarn(CACHE_VIOL,CACHE_ADDED);
});
  $("#menuNotify").addEventListener("click",async()=>{
    NOTIFY=!NOTIFY;
    localStorage.setItem("mchat_notify",NOTIFY?"1":"0");
    if(NOTIFY&&"Notification" in window&&Notification.permission==="default"){
      try{await Notification.requestPermission();}catch(e){}
    }
    syncNotifyBtn();
    setMenu(false);
    toast(NOTIFY?"已开启提醒（页面开着时生效）":"已关闭提醒");
  });
  $("#menuProgress").addEventListener("click",()=>{
    SHOW_PROGRESS=!SHOW_PROGRESS;
    try{localStorage.setItem("mchat_prog",SHOW_PROGRESS?"1":"0");}catch(e){}
    syncProgressBtn();
    setMenu(false);
    renderDialog(CACHE);
    setDiag();
    toast(SHOW_PROGRESS?"显示 dsh 进度流":"已隐藏 dsh 进度流");
  });
  syncNotifyBtn();
  syncProgressBtn();
document.body.dataset.theme=THEME;
renderThemeDots();
renderTargets();
  refreshRouteHint();
  autoGrow();
  $("#panelBtn").addEventListener("click",()=>{
    topEl.dataset.clicks=String(Number(topEl.dataset.clicks||0)+1);
    togglePanel();
  });
  $("#titleBtn").addEventListener("click",()=>setMenu(!menuIsOpen()));
  $("#menuBtn").addEventListener("click",()=>setMenu(!menuIsOpen()));
  $("#menuSearch").addEventListener("click",openSearch);
  $("#menuPanel").addEventListener("click",()=>{
    setMenu(false);
    if(panelLocked)unlockPanel();else setPanel(!panelOpen,true);
  });
$("#searchCancel").addEventListener("click",closeSearch);
$("#menuContacts").addEventListener("click",openContacts);
$("#menuTask").addEventListener("click",()=>{setMenu(false);openTaskPage();});
$("#taskCancel").addEventListener("click",closeTaskPage);
$("#taskAddAcc").addEventListener("click",()=>taskAccAdd(""));
$("#taskSubmit").addEventListener("click",submitTask);
$("#contactsCancel").addEventListener("click",closeContacts);
$("#contactsFilter").addEventListener("input",(e)=>renderContacts(e.target.value));
$("#groupCancel").addEventListener("click",closeGroupPage);
$("#groupCreate").addEventListener("click",createGroup);
  $("#searchInput").addEventListener("input",(e)=>renderSearch(e.target.value));
  $("#jump").addEventListener("click",jumpToBottom);
  $("#newPill").addEventListener("click",jumpToBottom);
  // 点空白处收起菜单
  document.addEventListener("click",(e)=>{
    if(!menuIsOpen())return;
    const t=e.target;
    // ★ 允许列表里**必须**带上开菜单的那两个开关本身，否则"先开、再被同一击关掉"：
    //   点标题（#titleBtn）曾因此**永远打不开菜单**——它自己有 toggle 处理器，但事件冒泡到这里
    //   又立刻 setMenu(false)（2026-09-13 在 ui_check 里抓到，点 ⋯ 能开、点标题不能）。
    if(t.closest&&(t.closest("#menu")||t.closest("#menuBtn")||t.closest("#titleBtn")))return;
    setMenu(false);
  });
// 往下翻消息 -> 收起面板让位；往上翻 / 回到顶部 -> 放出来
// ★ 折叠防抖（老板 2026-09-11 23:0x：上下滑动时面板"疯狂颤抖"，折叠展开折叠展开）：
//   老实现只看单次 dy>8 就切，而且 setPanel() 会改布局 → 又触发 scroll → 形成
//   "收起→布局变→滚动→展开"的**死循环**。三道护栏：
//   ① 同方向要**持续** PANEL_SETTLE_MS 才动（方向一变就重新计时）——抖一下不算
//   ② 切完 **冷却** PANEL_COOLDOWN_MS，期间再滚也不切
//   ③ 切完把"自己引起的那次布局滚动"屏蔽 PANEL_SETTLE_MS（suppressAutoUntil）
const PANEL_SETTLE_MS=260;
const PANEL_COOLDOWN_MS=700;
let lastY=0,panelDir=0,panelDirSince=0,panelCooldownUntil=0;
  boardEl.addEventListener("scroll",()=>{
    const y=boardEl.scrollTop;
    if(atBottom())hideNewPill();
    updateJump();
    const now=Date.now();
    const dy=y-lastY;
    lastY=y;
    if(panelLocked||now<suppressAutoUntil)return;      // 手动按过 / 刚被程序滚动过
    if(Math.abs(dy)<2)return;                          // 微小抖动直接忽略
    const dir=dy>0?1:-1;
    if(dir!==panelDir){panelDir=dir;panelDirSince=now;return;}   // 方向刚变：重新计时
    if(now-panelDirSince<PANEL_SETTLE_MS)return;       // 同向不够久：等
    if(now<panelCooldownUntil)return;                  // 冷却中：别切
    const want=(y<=4)?true:(dir<0);                    // 回到顶部 / 往上翻 → 展开
    if(want!==panelOpen&&(want||y>60)){
      setPanel(want);
      panelCooldownUntil=now+PANEL_COOLDOWN_MS;
      suppressAutoUntil=now+PANEL_SETTLE_MS;           // 屏蔽自己引起的那次布局滚动
    }
  },{passive:true});
// 手机切回前台 / 网络恢复时立刻补一次同步
document.addEventListener("visibilitychange",()=>{if(!document.hidden)load();});
window.addEventListener("online",()=>load());
load();
// —— HUB-007 实时通道（SSE）——
// 服务端一有变化（新记录/公告/任务/暂停状态）就推一条**无载荷**的 changed；收到就拉一次（去抖 300ms）。
// 轮询降级成 **30 秒兜底**：断线、拒连、老浏览器都能自愈。没有 token 时订阅也不触发 load（免得反复弹口令框）。
let SSE_DEBOUNCE=null,SSE_OK=false;
(function(){
  try{
    if(typeof EventSource==="undefined")return;
    const es=new EventSource("/api/events");
    es.addEventListener("open",()=>{SSE_OK=true;});
    es.addEventListener("changed",()=>{
      if(!token)return;
      if(SSE_DEBOUNCE)clearTimeout(SSE_DEBOUNCE);
      SSE_DEBOUNCE=setTimeout(()=>{load();},300);
    });
    es.addEventListener("error",()=>{SSE_OK=false;});   // 浏览器自己按 retry: 重连
  }catch(e){}
})();
setInterval(load,30000);
</script>
</body>
</html>`;

async function main() {
  ensureDataDir();
  ensureBoardFile();
 ensureDialogFile();
 ensureAgentsFile();
  loadDialogArchive(); // 轮转后的历史先进内存，读端才"看得见全史"
 loadDialogIds();
  initialDialogImport();
  loadRoutedIds();
  const token = readToken();

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://" + HOST);

    if (req.method === "GET" && (url.pathname === "/" || url.pathname === "/board")) {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" });
      res.end(PAGE);
      return;
    }
    if (req.method === "GET" && url.pathname === "/api/ping") {
      sendJson(res, 200, {
        ok: true,
        busy,
        ver: PAGE_VER,
        aliases: taskIdAliases(),
        codexBin: resolveCodexBin(), // 排障用：确认 Hub 找到的是哪个 codex.exe（别写死版本哈希）
      });
      return;
    }

    // ── HUB-007 实时通道（SSE）：**不要求 token，也不带任何数据** ──
    // 只推"变了"这个事实（真源仍走 REST /api/dialog）；这样即使 URL 被日志记下也不泄内容。
    if (req.method === "GET" && url.pathname === "/api/events") {
      res.writeHead(200, {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-store",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      });
      // retry 给浏览器自动重连节拍；开头一条注释行让客户端立刻确认"连上了"
      res.write("retry: 3000\n\n: connected\n\n");
      sseClients.add(res);
      const ping = setInterval(() => {
        try {
          res.write(": ping\n\n");
        } catch {
          clearInterval(ping);
          sseClients.delete(res);
        }
      }, 20000);
      req.on("close", () => {
        clearInterval(ping);
        sseClients.delete(res);
      });
      log("SSE CLIENT +", sseClients.size);
      return;
    }

    // 客户端引导：**不需要 token**（只暴露版本/能力，不含任何数据）。
    // 未来的 App/脚本先打这个口，再决定用哪些接口——这样"加接口"永远不会弄坏老客户端。
    if (req.method === "GET" && url.pathname === "/api/meta") {
      sendJson(res, 200, { ok: true, ...capabilities() });
      return;
    }

    // 页面体检上报：**故意不要求 token**——页面连 token 都没有时正是最需要诊断的时候。
    // 只覆盖一个小的 json 文件，写入内容由 readBody 限长（20KB）。
    if (req.method === "POST" && url.pathname === "/api/uireport") {
      let payload = {};
      try {
        payload = JSON.parse((await readBody(req)) || "{}");
      } catch {
        payload = { parseError: true };
      }
      let prev = {};
      try {
        prev = JSON.parse(fs.readFileSync(UI_REPORT_FILE, "utf8"));
      } catch {}
      const rec = {
        at: fmtNow(),
        seq: Number(prev.seq || 0) + 1,
        ua: String(req.headers["user-agent"] || "").slice(0, 140),
        ...payload,
      };
      try {
        fs.mkdirSync(path.dirname(UI_REPORT_FILE), { recursive: true });
        fs.writeFileSync(UI_REPORT_FILE, JSON.stringify(rec, null, 2), "utf8");
      } catch (e) {
        log("UI REPORT WRITE FAILED:", e.message);
      }
      sendJson(res, 200, { ok: true, seq: rec.seq });
      return;
    }

    const headerToken = req.headers["x-mchat-token"] || "";
    if (!tokensEqual(headerToken, token)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }

    if (req.method === "GET" && url.pathname === "/api/board") {
      ensureBoardFile();
      sendJson(res, 200, { content: fs.readFileSync(BOARD_FILE, "utf8"), updatedAt: fmtNow() });
      return;
    }

    // 排障 / 自测口：**只读**返回某条线的投递判定（HUB-002 的纯函数，无副作用、不投递）。
    // 例：/api/deliver?alias=codex-看板服务 → { action: inject|mailbox|backoff|duty|retired|unknown, reason, ... }
    if (req.method === "GET" && url.pathname === "/api/deliver") {
      const alias = resolveTarget(String(url.searchParams.get("alias") || "").trim());
      if (!alias) {
        sendJson(res, 400, { error: "要带 ?alias=看板名" });
        return;
      }
      try {
        sendJson(res, 200, { ok: true, ...decideDelivery(alias) });
      } catch (e) {
        sendJson(res, 500, { error: String((e && e.message) || e) });
      }
      return;
    }

    // ── HUB-001 实例绑定 / 换绑（不再手改 agents.json；换绑留痕）──
    //   换绑时把旧 threadId 记进 failedThreadIds，并写明归档原因（审计用）；
    //   绑定成功即 status=active（NEW_EMPLOYEE_RUNBOOK 阶段 2 那一步的机器化）。
    // ── HUB-001 入职：给一条**新线**发牌（登记名册） ──────────────────────────
    //   为什么单独开一个口：`/api/bind` 只能在**已入册**的名字上换绑，新建员工没有路径——
    //   于是"新窗口"既不能被派活、也不能被信箱/门铃叫醒（老板 2026-09-13："走个员工流程"）。
    //   三条硬规矩：
    //     ① **工号永不复用**（在册 slug / `slugAliases` 的历史工号 / 退役条目全都不许撞）；
    //     ② **一个会话只属于一条线**（threadId 已被别人绑 → 409，指出是谁）；
    //     ③ **必须写清批准人**（入职=发牌；按红线"给别人放权"只有老板能拍板，接口不接受没批准人的登记）。
    //   写入走唯一入口 updateAgents（读前/写前 (mtime,size) 校验，冲突宁可 409 不覆盖）。
    if (req.method === "POST" && url.pathname === "/api/onboard") {
      let payload = {};
      try {
        payload = JSON.parse((await readBody(req)) || "{}");
      } catch {}
      const cfg0 = readAgents();
      const names = Object.keys(cfg0.agents || {});
      const norm = (v) => String(v || "").trim().replace(/^@/, "").toLowerCase();
      const by = names.find((n) => n.toLowerCase() === norm(payload.by)) || "";
      const name = String(payload.name || "").trim().replace(/^@/, "");
      const slug = norm(payload.slug);
      const approval = String(payload.approval || "").trim();
      const tid = String(payload.threadId || "").trim();
      if (!by) return sendJson(res, 400, { error: "by 必须是**你自己的注册看板名**（谁办的写在看板行里）", hint: names.join("、") });
      if (!approval) return sendJson(res, 400, { error: "缺 approval：入职=发牌，必须写清谁批准的（如「老板 2026-09-13 口述」）" });
      if (name.length < 3 || name.length > 40) return sendJson(res, 400, { error: "名字长度要在 3–40 之间" });
      if (GENERIC_BOARD_NAMES.includes(name.toLowerCase())) return sendJson(res, 400, { error: "名字不能是泛称：" + name });
      if (names.some((n) => n.toLowerCase() === name.toLowerCase())) return sendJson(res, 409, { error: "这个名字已注册：" + name, hint: "换绑请用 POST /api/bind" });
      // 没给工号 → 按跨系统契约兜底派生（套件仓 docs/slug.md；显式给的仍然优先）
      const finalSlug = slug || makeSlug(name);
      if (!/^[a-z0-9][a-z0-9-]{1,30}$/.test(finalSlug)) return sendJson(res, 400, { error: "工号 slug 格式不对（小写字母/数字/连字符，2–31 位）", hint: "没给就按契约派生，派生出的是：" + finalSlug });
      const holder = Object.entries(cfg0.agents || {}).find(([, m]) => String((m || {}).slug || "").toLowerCase() === finalSlug);
      if (holder) return sendJson(res, 409, { error: "工号已被占用：" + finalSlug, hint: "现役：" + holder[0] });
      const aliased = Object.keys(cfg0.slugAliases || {}).find((k) => String(k).toLowerCase() === finalSlug);
      if (aliased) return sendJson(res, 409, { error: "工号已退役、永不复用：" + finalSlug, hint: "历史岗位：" + cfg0.slugAliases[aliased] });
      if (tid) {
        if (!/^[0-9a-fA-F-]{36}$/.test(tid)) return sendJson(res, 400, { error: "threadId 格式不对（要 UUID）" });
        const used = Object.entries(cfg0.agents || {}).find(([, m]) => String((m || {}).threadId || "") === tid);
        if (used) return sendJson(res, 409, { error: "这个会话已经绑在别的线上：" + used[0], hint: "一个会话只属于一条线" });
      }
      const wr = updateAgents(
        (cfg) => {
          const agents = cfg.agents || (cfg.agents = {});
          if (agents[name]) return false; // 重放着拦一次（幂等）
          agents[name] = {
            label: name,
            title: String(payload.title || "").trim().slice(0, 40) || "新入职",
            slug: finalSlug,
            workspace: String(payload.workspace || "").trim() || WORKSPACE,
            status: tid ? "active" : "unknown",
            ...(tid ? { threadId: tid } : {}),
            ...(payload.level ? { level: String(payload.level).slice(0, 16) } : {}),
            ...(payload.duty === true ? {} : { duty: false }),
            note:
              "入职登记（" + fmtNow().slice(0, 16) + "，by " + by + "，批准：" + approval.slice(0, 60) + "）" +
              (payload.note ? "；" + String(payload.note).slice(0, 120) : ""),
          };
          return true;
        },
        { backup: true }
      );
      if (!wr.ok) return sendJson(res, 409, { error: "名册正被其他进程修改，本次未写入（请重试）", detail: wr });
      // ★ HUB-015(a)：入职时把**当前生效中的公告正文**补投给新线（走既有信箱口）。
      //   口径不变（d）：仍是"当前名册 × 生效公告"，新人对生效公告**照样要回执**；
      //   补的只是"送到"这半步——它得先收到正文，才谈得上回执。同时记下投递时刻，
      //   让它对每条公告的 24h 回执窗口从**自己收到那一刻**起算（(b)）。
      let noticesGiven = 0;
      try {
        const stillActive = applyNoticeAcks(readDialog(600).map(normalizeRecordNames))
          .filter((r) => r.kind === "notice" && r.refs && r.refs.active);
        for (const n of stillActive) {
          const code = noticeCode(n.id);
          const tip =
            "【公告 " + code + "（补投 · 你入职时仍在生效）】" + String(n.body || "") +
            "\n\n请回执：在看板回一行 `收到 " + code + "`（或点引用回复那条公告再回「收到」）。**每条公告都要单独回执**。";
          try {
            fs.appendFileSync(
              path.join(MAILBOX_DIR, "pending_" + slugFor(name) + ".ndjson"),
              JSON.stringify({ ts: fmtNow(), from: CODEX_SERVICE, to: name, body: tip }) + "\n",
              "utf8"
            );
            markNoticeDelivered(n.id, name);
            noticesGiven++;
          } catch {}
        }
      } catch {}
      if (noticesGiven) log("ONBOARD NOTICE BACKFILL:", name, "公告=" + noticesGiven);
      appendBoardLine(
        "老板",
        CODEX_SERVICE,
        "（系统：@" + by + " 给 **" + name + "** 办了入职（批准：" + approval + "）：工号 " + finalSlug +
          (tid ? "，会话 " + tid.slice(0, 8) + "…" : "，未绑会话") + "）"
      );
      log("ONBOARD:", name, "slug=" + finalSlug, "by=" + by, tid ? "thread=" + tid.slice(0, 8) : "no-thread");
      sendJson(res, 200, { ok: true, name: name, slug: finalSlug, threadId: tid || null, by: by, slugDerived: !slug, noticesDelivered: noticesGiven });
      return;
    }

    if (req.method === "POST" && url.pathname === "/api/bind") {
      let payload = {};
      try {
        payload = JSON.parse((await readBody(req)) || "{}");
      } catch {}
      const names = Object.keys(readAgents().agents || {});
      const want = String(payload.alias || "").trim().replace(/^@/, "").toLowerCase();
      const alias = names.find((n) => n.toLowerCase() === want) || "";
      const tid = String(payload.threadId || "").trim();
      if (!alias) {
        sendJson(res, 400, { error: "alias 没注册", hint: names.join("、") });
        return;
      }
      if (!/^[0-9a-fA-F-]{36}$/.test(tid)) {
        sendJson(res, 400, { error: "threadId 格式不对（要 UUID）" });
        return;
      }
      const before = readAgents().agents[alias] || {};
      const old = before.threadId ? String(before.threadId) : "";
      // 走唯一写入口（乐观并发；mutator 幂等，可能被重放）
      const wr = updateAgents(
        (cfg) => {
          const agents = cfg.agents || (cfg.agents = {});
          const meta = { ...(agents[alias] || {}) };
          const prev = meta.threadId ? String(meta.threadId) : "";
          if (prev && prev !== tid) meta.failedThreadIds = [...new Set([...(meta.failedThreadIds || []), prev])];
          meta.threadId = tid;
          meta.status = "active";
          meta.note =
            (String(payload.note || "").slice(0, 160) || "绑定更新 " + fmtNow()) +
            (prev && prev !== tid ? "（旧实例 " + prev.slice(0, 8) + " 已归档，原因：" + String(payload.why || "换绑").slice(0, 80) + "）" : "");
          agents[alias] = meta;
          return true;
        },
        { backup: true }
      );
      if (!wr.ok) {
        sendJson(res, 409, { error: "名册正被其他进程修改，本次未写入（请重试）", detail: wr });
        return;
      }
      appendBoardLine("老板", CODEX_SERVICE, "（系统：@" + alias + " 绑定 → " + tid.slice(0, 8) + "…" + (old ? "（换绑，旧号已归档）" : "") + "）");
      log("BIND:", alias, "->", tid, old ? "(换绑 from " + old.slice(0, 8) + ")" : "(新绑)");
      sendJson(res, 200, { ok: true, alias: alias, threadId: tid, replaced: old || null });
      return;
    }

    // ── HUB-010 群组：读 / 注入（幂等 upsert） ──
    if (req.method === "GET" && url.pathname === "/api/groups") {
      const all = listGroups(!!url.searchParams.get("all"));
      const withAv = all.map((g) => ({ ...g, avatar: avatarOf(g.name) }));
      sendJson(res, 200, { ok: true, count: withAv.length, groups: withAv });
      return;
    }
    if (req.method === "POST" && url.pathname === "/api/groups") {
      let p = {};
      try {
        p = JSON.parse((await readBody(req)) || "{}");
      } catch {
        sendJson(res, 400, { error: "格式不对" });
        return;
      }
      const cfgA = readAgents().agents || {};
      const namesA = Object.keys(cfgA);
      const byRaw = String(p.by || "").trim().replace(/^@/, "").toLowerCase();
      const by = namesA.find((n) => n.toLowerCase() === byRaw || String((cfgA[n] || {}).slug || "").toLowerCase() === byRaw) || "";
      if (!by) return sendJson(res, 400, { error: "by 必须是注册看板名（注入方要实名）", hint: namesA.join("、") });
      const name = String(p.name || "").trim();
      if (name.length < 2 || name.length > 40) return sendJson(res, 400, { error: "群名 2–40 字" });
      const id = String(p.id || "").trim() || groupIdOf(name);
      const members = [...new Set((Array.isArray(p.members) ? p.members : []).map((m) => resolveTarget(String(m || "").trim())).filter((m) => namesA.includes(m)))];
      if (!members.length) return sendJson(res, 400, { error: "至少要有一个**已注册**的成员", hint: namesA.join("、") });
      const g = readGroups();
      const prev = g.groups[id] || {};
      const now = toCst(new Date());
      g.groups[id] = {
        id: id,
        name: name,
        members: members,
        note: String(p.note || prev.note || "").slice(0, 200),
        source: String(p.source || prev.source || "api").slice(0, 40),
        by: by,
        createdAt: prev.createdAt || now,
        updatedAt: now,
        removed: p.removed === true ? true : false,
      };
      writeGroups(g);
      log("GROUP UPSERT:", id, name, members.length + " 人", "by=" + by, p.removed === true ? "(removed)" : "");
      sendJson(res, 200, {
        ok: true,
        id: id,
        created: !prev.id,
        group: { ...g.groups[id], avatar: avatarOf(name) },
      });
      return;
    }

    // ── HUB-012 员工：套件员工卡（真源）+ 运行态 + 本 Hub 运行态 ──
    if (req.method === "GET" && url.pathname === "/api/employees") {
      catchUpDialog();
      const list = buildEmployees();
      sendJson(res, 200, {
        ok: true,
        count: list.length,
        kitDir: KIT_DIR,
        byLevel: list.reduce((m, e) => ((m[e.level] = (m[e.level] || 0) + 1), m), {}),
        employees: list,
      });
      return;
    }
    // ── HUB-012 物料 / 节点（时间轴）：项目的"物料与历程"  ──
    if (req.method === "GET" && url.pathname === "/api/items") {
      const q = (k) => String(url.searchParams.get(k) || "").trim();
      const project = q("project");
      const line = q("line");
      const kind = q("kind");
      const fromTs = q("from");
      const toTs = q("to");
      const limit = Math.min(Number(q("limit") || 500), 2000);
      let items = readItems(0);
      if (project) items = items.filter((x) => String(x.project || "") === project);
      if (line) items = items.filter((x) => String(x.line || "") === line);
      if (kind) items = items.filter((x) => String(x.kind || "") === kind);
      if (fromTs) items = items.filter((x) => String(x.ts || "") >= fromTs);
      if (toTs) items = items.filter((x) => String(x.ts || "") <= toTs);
      items = items.slice(-limit);
      const byKind = {};
      for (const x of items) byKind[x.kind] = (byKind[x.kind] || 0) + 1;
      sendJson(res, 200, { ok: true, count: items.length, byKind: byKind, items: items });
      return;
    }
    if (req.method === "POST" && url.pathname === "/api/items") {
      let p = {};
      try {
        p = JSON.parse((await readBody(req)) || "{}");
      } catch {
        sendJson(res, 400, { error: "格式不对" });
        return;
      }
      const names = Object.keys(readAgents().agents || {});
      const byRaw = String(p.by || "").trim().replace(/^@/, "").toLowerCase();
      const by = names.find((n) => n.toLowerCase() === byRaw || String((readAgents().agents[n] || {}).slug || "").toLowerCase() === byRaw) || "";
      if (!by) return sendJson(res, 400, { error: "by 必须是注册看板名（谁记的这条）", hint: names.join("、") });
      const project = String(p.project || "").trim().toUpperCase();
      const kind = String(p.kind || "node").trim().toLowerCase();
      const title = String(p.title || "").trim();
      if (!project) return sendJson(res, 400, { error: "要给 project（项目/模块，如 HUB / KIT）" });
      if (!ITEM_KINDS.includes(kind)) return sendJson(res, 400, { error: "kind 不合法", hint: ITEM_KINDS.join("/") });
      if (!title) return sendJson(res, 400, { error: "要给 title" });
      const ts = toCst(new Date());
      const it = {
        v: "items.v1",
        id: dialogIdFor("item|" + project + "|" + kind + "|" + title + "|" + ts),
        ts: ts,
        from: by,
        project: project,
        line: String(p.line || "").trim(),
        kind: kind,
        title: title,
        body: String(p.body || "").slice(0, 2000),
        path: String(p.path || "").trim(),
        url: String(p.url || "").trim(),
        tags: Array.isArray(p.tags) ? p.tags.map((t) => String(t).slice(0, 24)).slice(0, 8) : [],
        ref: String(p.ref || "").trim(),
      };
      appendItem(it);
      log("ITEM ADDED:", project, kind, title.slice(0, 40), "by=" + by);
      sendJson(res, 200, { ok: true, item: it });
      return;
    }
    // ── HUB-012 多来源归一：不管是看板、txt、套件、还是别的脚本，进来都是**同一种记录** ──
    if (req.method === "POST" && url.pathname === "/api/ingest") {
      let p = {};
      try {
        p = JSON.parse((await readBody(req)) || "{}");
      } catch {
        sendJson(res, 400, { error: "格式不对" });
        return;
      }
      const names = Object.keys(readAgents().agents || {});
      const fromRaw = String(p.from || "").trim().replace(/^@/, "").toLowerCase();
      const from = names.find((n) => n.toLowerCase() === fromRaw || String((readAgents().agents[n] || {}).slug || "").toLowerCase() === fromRaw) || "";
      const body = String(p.body || "").trim();
      const to = p.to ? resolveTarget(String(p.to)) : "";
      if (!from) return sendJson(res, 400, { error: "from 必须实名（注册看板名）——不同来源可以不同，但**署名不能匿名**", hint: names.join("、") });
      if (!body) return sendJson(res, 400, { error: "body 不能为空" });
      const rec = {
        id: dialogIdFor("ingest|" + (p.source || "") + "|" + (p.ref || "") + "|" + from + "|" + body.slice(0, 80) + "|" + Date.now()),
        ts: toCst(new Date()),
        from: from,
        to: to || "老板",
        channel: "ingest",
        kind: ["message", "task", "report", "notice"].includes(String(p.kind)) ? String(p.kind) : "message",
        body: redact(clip(body, 4000)),
        threadId: null,
        refs: { source: String(p.source || "unknown").slice(0, 40), ref: String(p.ref || "").slice(0, 200) },
        state: "done",
      };
      const added = appendDialog(rec);
      log("INGEST:", rec.refs.source, from, "->", rec.to, added ? "(new)" : "(dup)");
      sendJson(res, 200, { ok: true, id: rec.id, added: added, to: rec.to });
      return;
    }

    // ── HUB-011 服务端已读位置（多设备同步的地基）──
    //   手机页现在把"看到哪儿"存在浏览器 localStorage 里——换设备就丢。这里让每个客户端
    //   上报自己的游标（deviceId + upToId），将来 App/多端可以用同一份已读状态。
    if (req.method === "POST" && url.pathname === "/api/read") {
      let p = {};
      try {
        p = JSON.parse((await readBody(req)) || "{}");
      } catch {
        sendJson(res, 400, { error: "格式不对" });
        return;
      }
      const dev = String(p.deviceId || "").trim().slice(0, 64);
      const upTo = String(p.upToId || "").trim();
      if (!dev || !upTo) return sendJson(res, 400, { error: "要 deviceId 和 upToId" });
      const st = readReadState();
      st.devices[dev] = { upToId: upTo, at: toCst(new Date()) };
      writeReadState(st);
      sendJson(res, 200, { ok: true, deviceId: dev, upToId: upTo });
      return;
    }

    // ── HUB-009 联系人（通讯录）：头像 + 职责 + 状态 + 未读/信箱 + 最后一句 ──
    // 给"专业 App"用的名册接口：前端拿它画联系人页；点一条就能给那条线发消息。
    if (req.method === "GET" && url.pathname === "/api/contacts") {
      catchUpDialog();
      const raw2 = readDialog(600);
      const all2 = applyClaimStates(raw2.map(normalizeRecordNames));
      const cfg2 = readAgents();
      const contacts = Object.entries(cfg2.agents || {}).map(([alias, meta]) => {
        const authored = all2.filter(
          (r) => String(r.from || "").toLowerCase() === alias && !/^〔代答〕/.test(String(r.body || ""))
        );
        const last = authored[authored.length - 1] || null;
        const open = all2.filter((r) => {
          if (String(r.to || "").toLowerCase() !== alias) return false;
          if (String(r.from || "").toLowerCase() === alias) return false;
          if (r.kind === "progress") return false;
          return r.state !== "done" && r.state !== "failed";
        }).length;
        // 未读口径统一走 lastOwnStatementTs（与 /api/dialog、/api/employees 同一个函数）
        const lastSeen = lastOwnStatementTs(alias, all2);
        const ageMs = lastSeen ? Date.now() - parseCst(lastSeen) : null;
        return {
          alias: alias,
          label: meta.label || alias,
          title: meta.title || "",
          note: normalizeTaskIds(String(meta.note || "").split("；")[0].slice(0, 60)),
          status: String(meta.status || "").toLowerCase() === "retired" ? "retired" : ageMs == null ? "none" : ageMs < 3 * 3600e3 ? "active" : ageMs < 24 * 3600e3 ? "idle" : "stale",
          retired: String(meta.status || "").toLowerCase() === "retired",
          duty: dutyEnabled(alias),
          pendingMail: pendingMailFor(alias, lastSeen),
          open: open,
          avatar: avatarOf(alias),
          lastMsg: last ? { ts: String(last.ts), body: String(last.body || "").slice(0, 60) } : null,
        };
      });
      sendJson(res, 200, { ok: true, count: contacts.length, contacts: contacts, updatedAt: fmtNow() });
      return;
    }

    // ── HUB-008 任务表：卡（docs/tasks/*.md）+ 派单（inbox）合成一张表，按前缀分组当项目 ──
    if (req.method === "GET" && url.pathname === "/api/tasks") {
      const table = buildTaskTable();
      sendJson(res, 200, { ok: true, ...table });
      return;
    }
    // 建卡（HUB-004 的后端）：自动取号 → 落标准模板 → 投信箱 → 看板留痕 → 尽力唤醒
    if (req.method === "POST" && url.pathname === "/api/tasks") {
      let p = {};
      try {
        p = JSON.parse((await readBody(req)) || "{}");
      } catch {
        sendJson(res, 400, { error: "格式不对" });
        return;
      }
      const names = Object.keys(readAgents().agents || {});
      const pick = (v) => {
        const q = String(v || "").trim().replace(/^@/, "").toLowerCase();
        return names.find((n) => n.toLowerCase() === q || String((readAgents().agents[n] || {}).slug || "").toLowerCase() === q) || "";
      };
      const author = pick(p.author);
      const assignee = pick(p.assignee);
      const title = String(p.title || "").trim();
      const acceptance = (Array.isArray(p.acceptance) ? p.acceptance : [p.acceptance]).map((x) => String(x || "").trim()).filter(Boolean);
      const prefix = String(p.prefix || "HUB").trim().toUpperCase();
      const kind = String(p.kind || "dev").trim();
      const priority = String(p.priority || "P2").trim();
      if (!author) return sendJson(res, 400, { error: "author 必须是注册看板名", hint: names.join("、") });
      if (!assignee) return sendJson(res, 400, { error: "assignee 必须是注册看板名", hint: names.join("、") });
      if (title.length < 4) return sendJson(res, 400, { error: "标题太短" });
      if (!acceptance.length) return sendJson(res, 400, { error: "**没有验收标准不许派**（至少一条）" });
      if (!TASK_PREFIXES.includes(prefix)) return sendJson(res, 400, { error: "前缀不在登记表里：" + prefix, hint: TASK_PREFIXES.join("、") });
      const id = nextTaskId(prefix);
      const cardPath = path.join(TASKS_DIR, id + ".md");
      if (fs.existsSync(cardPath)) return sendJson(res, 409, { error: "卡已存在：" + id });
      const card = taskCardTemplate({ id, title, author, assignee, kind, priority, acceptance, goal: String(p.goal || "").trim(), scope: String(p.scope || "").trim(), due: String(p.due || "").trim() });
      try {
        fs.mkdirSync(TASKS_DIR, { recursive: true });
        fs.writeFileSync(cardPath, card, "utf8");
      } catch (e) {
        return sendJson(res, 500, { error: "写卡失败：" + e.message });
      }
      const summary = "【派单 " + id + "】" + title + "\n卡：`docs/tasks/" + id + ".md`\n验收：" + acceptance.map((a, i) => (i + 1) + ") " + a).join("；") + "\n请认领并在看板回一行；完成后把卡的状态改掉（POST /api/tasks/status）。";
      // 投它信箱 + 尽力唤醒（走统一投递口：queue 优先）
      try {
        fs.appendFileSync(path.join(MAILBOX_DIR, "pending_" + slugFor(assignee) + ".ndjson"), JSON.stringify({ ts: fmtNow(), from: author, to: assignee, body: summary }) + "\n", "utf8");
      } catch {}
      const dv = await deliverToLine(assignee, "（看板派单，来自 " + author + "）" + summary)
        .catch((e) => ({ ok: false, how: "error", error: String((e && e.message) || e) }));
      // ★ HUB-004 §四之一（总监 2026-09-11 05:4x 追加）：提交后**立刻**给出这条单的投递结论，
      //   三态之一，依据直接复用 HUB-002 的排障口（decideDelivery）——不许只回一句"提交成功"，
      //   否则老板分不清这单是"有人接"还是"压在信箱里"。
      const verdict = decideDelivery(assignee);
      const dstate = dv.ok
        ? "woken"
        : dv.how === "no-thread"
          ? "mailbox"
          : verdict.action === "inject"
            ? "not-woken"
            : "mailbox";
      const dtext =
        dstate === "woken"
          ? "已叫醒，它本人已接手"
          : dstate === "not-woken"
            ? "已投递未唤醒（" + (verdict.reason || dv.error || dv.how || "投递未成功") + "）——留言在它信箱"
            : "已落它信箱，未叫醒（" + (verdict.reason || dv.how || "没绑定会话") + "）";
      appendBoardLine(
        "老板",
        CODEX_SERVICE,
        "（系统：@" + author + " 派单 **" + id + "** → @" + assignee + "：" + title + "｜" + dtext + "）"
      );
      log("TASK CREATED:", id, "->", assignee, dstate, "by=" + author);
      sendJson(res, 200, {
        ok: true,
        id: id,
        file: "docs/tasks/" + id + ".md",
        assignee: assignee,
        delivered: dstate === "woken",
        delivery: { status: dstate, text: dtext, how: dv.how || "", reason: verdict.reason || "" },
      });
      return;
    }
    // 状态流转（写侧车，不改卡；卡是规范真源，运行态是投影）
    if (req.method === "POST" && url.pathname === "/api/tasks/status") {
      let p = {};
      try {
        p = JSON.parse((await readBody(req)) || "{}");
      } catch {
        sendJson(res, 400, { error: "格式不对" });
        return;
      }
      const names = Object.keys(readAgents().agents || {});
      const id = String(p.id || "").trim().toUpperCase();
      const state = String(p.state || "").trim().toLowerCase();
      const by = names.find((n) => n.toLowerCase() === String(p.by || "").trim().replace(/^@/, "").toLowerCase()) || "";
      if (!by) return sendJson(res, 400, { error: "by 必须是注册看板名" });
      if (!TASK_STATES.includes(state)) return sendJson(res, 400, { error: "状态不合法", hint: TASK_STATES.join("/") });
      const st = readTasksState();
      st[id] = { state: state, by: by, at: toCst(new Date()), note: String(p.note || "").slice(0, 200) };
      writeTasksState(st);
      if (state === "done" || state === "blocked") {
        appendBoardLine("老板", CODEX_SERVICE, "（系统：任务 **" + id + "** → " + state + "（by " + by + "）" + (p.note ? " · " + String(p.note).slice(0, 60) : "") + "）");
      }
      sendJson(res, 200, { ok: true, id: id, state: state, by: by });
      return;
    }

    // ── HUB-006 暂停闸：置闸（S1/S2 或涉及钱；也可由线手动上报）──
    //    解除**没有** API——只能是老板在看板发的 `@全体 【解除暂停】…` 公告。
    if (req.method === "POST" && url.pathname === "/api/halt") {
      let payload = {};
      try {
        payload = JSON.parse((await readBody(req)) || "{}");
      } catch {}
      const names = Object.keys(readAgents().agents || {});
      const rq = String(payload.by || "").trim().replace(/^@/, "").toLowerCase();
      const by = names.find((n) => n.toLowerCase() === rq) || "";
      if (!by) {
        sendJson(res, 400, { error: "by 必须是注册看板名", hint: names.join("、") });
        return;
      }
      const h = setHalt(by, String(payload.severity || ""), String(payload.reason || ""), String(payload.taskId || ""));
      sendJson(res, 200, { ok: true, halt: h });
      return;
    }

    // ── HUB-003 向上敲门铃：只推三类事件，且**一律上板 @老板** ──
    if (req.method === "POST" && url.pathname === "/api/boss-event") {
      let payload;
      try {
        payload = JSON.parse((await readBody(req)) || "{}");
      } catch {
        sendJson(res, 400, { error: "格式不对" });
        return;
      }
      const names = Object.keys(readAgents().agents || {});
      const rq = String(payload.from || "").trim().replace(/^@/, "").toLowerCase();
      const from = names.find((n) => n.toLowerCase() === rq) || "";
      const kind = String(payload.kind || "").trim().toLowerCase();
      const needAction = String(payload.needAction || "").trim();
      const task = String(payload.task || "").trim().slice(0, 60);
      if (!from) {
        sendJson(res, 400, { error: "署名没注册（要写你自己的看板名）", hint: names.join("、") });
        return;
      }
      if (!BOSS_KINDS[kind]) {
        sendJson(res, 400, { error: "只推三类事件：accept（待验收）/ decide（需拍板）/ incident（故障）" });
        return;
      }
      if (needAction.length < 4) {
        sendJson(res, 400, { error: "每条必须写清「要你做什么」——没有动作的一律不发" });
        return;
      }
      const events = readBossEvents();
      const key = (task || from + "|" + kind).toLowerCase();
      const recent = events.find((e) => String(e.key) === key && Date.now() - parseCst(e.ts) < BOSS_THROTTLE_MS);
      if (recent) {
        sendJson(res, 200, {
          ok: true,
          throttled: true,
          sinceMin: Math.round((Date.now() - parseCst(recent.ts)) / 60000),
          reason: "同一任务 10 分钟内只推一次（节流）",
        });
        return;
      }
      if (bossTodayCount(events) >= BOSS_DAILY_MAX) {
        sendJson(res, 429, { ok: false, error: "今日「待老板」已达上限 " + BOSS_DAILY_MAX + " 条——急事请直接开那条线说" });
        return;
      }
      const ev = {
        v: "boss_events.v1",
        id: dialogIdFor("boss|" + key + "|" + Date.now()),
        ts: toCst(new Date()),
        from: from,
        kind: kind,
        task: task,
        needAction: needAction,
        key: key,
        // 记下"创建这一刻"老板最后一次发言的标记（见 bossPending 注释）
        ackMark: lastBossRecordId(readDialog(1000)),
      };
      appendBossEvent(ev);
      // ① 一律上板并 @老板：不许只压在某条线的信箱里
      appendBoardLine("老板", from, "【待老板·" + BOSS_KINDS[kind] + "】" + (task ? task + "：" : "") + needAction);
      log("BOSS EVENT:", kind, from, task, needAction.slice(0, 50));
      // HUB-006：S1/S2（或显式 halt:true）→ 自动置暂停闸
      const sev = String(payload.severity || "").trim().toUpperCase();
      if (kind === "incident" && (/^S[12]$/.test(sev) || payload.halt === true)) {
        setHalt(from, sev || "S1", task ? task + "：" + needAction : needAction, task);
      }
      sendJson(res, 200, { ok: true, id: ev.id, board: true, kindLabel: BOSS_KINDS[kind] });
      return;
    }
    // 静音开关：关掉的是"打扰"，**不是记录**（事件仍落盘、仍上板；界面要看得见已静音）
    if (req.method === "POST" && url.pathname === "/api/boss-mute") {
      let payload = {};
      try {
        payload = JSON.parse((await readBody(req)) || "{}");
      } catch {}
      const on = !!payload.on;
      writeState({ ...readState(), bossMuted: on });
      log("BOSS MUTE:", on);
      sendJson(res, 200, { ok: true, muted: on });
      return;
    }

    // 投递到某条线的"看板信箱"（**谁都能调用**：别的脚本/别的线都可以 POST 这个口）。
    // 只写信箱、不写看板行——本尊不在时由它自己的值守分线在看板回话。
    // ── 各线发帖的唯一正门：署名必须是注册看板名（泛称在这一步就被挡住，从根上不再进看板）──
    if (req.method === "POST" && url.pathname === "/api/post") {
      let payload;
      try {
        payload = JSON.parse((await readBody(req)) || "{}");
      } catch {
        sendJson(res, 400, { error: "格式不对" });
        return;
      }
      const rawAuthor = String(payload.author || "").trim();
      const body = String(payload.body || payload.message || "").trim();
      if (!rawAuthor || !body || body.length > 4000) {
        sendJson(res, 400, { error: "author/body 不合法（author 用你的看板名）" });
        return;
      }
      const cfg = readAgents().agents || {};
      const names = Object.keys(cfg);
      const lower = rawAuthor.toLowerCase().replace(/^@/, "");
      const GENERIC = GENERIC_BOARD_NAMES; // 共用一份黑名单（见模块顶部的定义）
      let alias = names.find((n) => n.toLowerCase() === lower) ||
        names.find((n) => String((cfg[n] || {}).slug || "").toLowerCase() === lower) ||
        names.find((n) => boardName(n).toLowerCase() === lower);
      if (GENERIC.includes(lower)) {
        // 泛称直接拒收：它就是"写的人没说自己是谁"，接受它等于把老问题合法化
        sendJson(res, 400, {
          error: "署名不能是泛称「" + rawAuthor + "」——必须写清是哪条线",
          hint: "注册的看板名：" + names.join("、"),
        });
        return;
      }
      if (!alias && boardName(rawAuthor) !== rawAuthor) alias = boardName(rawAuthor);
      if (!alias || !names.includes(alias)) {
        sendJson(res, 400, {
          error: "这个署名没注册：" + rawAuthor,
          hint: "注册的看板名：" + names.join("、"),
        });
        return;
      }
      const target = resolveTarget(String(payload.target || "老板").trim()) || "老板";
      appendBoardLine(target, alias, body);
      scheduleCheck();
      log("POST BY LINE:", alias, "->", target, body.slice(0, 40));
      sendJson(res, 200, { ok: true, author: alias, target: target });
      return;
    }

    if (req.method === "POST" && url.pathname === "/api/mail") {
      let payload;
      try {
        payload = JSON.parse((await readBody(req)) || "{}");
      } catch {
        sendJson(res, 400, { error: "格式不对" });
        return;
      }
      const to = resolveTarget(String(payload.to || "").trim());
      const from = boardName(String(payload.from || "老板").trim());
      const body = String(payload.body || payload.message || "").trim();
      if (!to || !body || body.length > 4000) {
        sendJson(res, 400, { error: "收件线或内容不合法" });
        return;
      }
      // HUB-013：旧工号不再可投递
      const roMail = retiredSlugOwner(payload.to);
      if (roMail) {
        sendJson(res, 400, { error: "这是退役工号，不再投递：" + to, hint: "请用岗位名 @" + roMail + "（同名即现任）" });
        return;
      }
      // 未注册的名字**没有信箱**：老实现会静默造一个 pending_<name>.ndjson（垃圾 + 静默丢）。
      // 按 I2「可寻址」把它挡在门口——要投信先登记（或走 /api/post 广播）。
      const namesMail = Object.keys(readAgents().agents || {});
      if (to !== "老板" && !namesMail.includes(to)) {
        sendJson(res, 400, {
          error: "这条线没登记，没有信箱可投：" + to,
          hint: "已注册：" + namesMail.join("、") + "；要广播请走 POST /api/post",
        });
        return;
      }
      queueForThread(to, { target: to.toLowerCase(), time: fmtNow(), author: from, content: body });
      // 默认**只投不唤醒**（I3：投递与唤醒分离；对方上线自读）。
      // 但"投了等于没投"是真实痛点（老板 2026-09-12 当场指出：发完没叫醒总监）。
      // 所以给一个**显式开关** `wake:true`：投完顺手走一次"投递即唤醒"（queue 优先，带冷却/上限）。
      // 不做成默认，是为了保住 I3 语义（投递与唤醒分离）、也给调用方选择权。
      let woke = false;
      let deduped = false;
      if (payload.wake === true) {
        try {
          const dv = await deliverByQueue(to, "（看板信箱来信提示 · 来自 " + from + "）你信箱里有一条：" + body.slice(0, 120) + "　请读 outputs/dialog/pending_" + slugFor(to) + ".ndjson 后回一句。");
          deduped = dv.how === "dup-skip";
          woke = !!dv.ok && !deduped;
          if (!woke && !deduped) {
            // 叫不醒不能**静默**：记一笔 + 排一次补投（复用 HUB-002 的退避补投，2 分钟后重试）
            log("MAIL WAKE MISS:", to, dv.how, dv.error ? String(dv.error).slice(0, 80) : "");
            const n = Number(wakeBook(to).attempts || 0);
            const wait = WAKE_BACKOFF_MS[Math.min(n, WAKE_BACKOFF_MS.length - 1)];
            setWakeBook(to, { attempts: n + 1, nextAt: Date.now() + wait, lastReason: "信箱来信唤醒失败:" + dv.how });
          }
        } catch {}
      }
      sendJson(res, 200, { ok: true, to: to, mailbox: "pending_" + slugFor(to) + ".ndjson", woke: woke, deduped: deduped });
      return;
    }

    if (req.method === "GET" && url.pathname === "/api/dialog") {
      catchUpDialog();
      const limit = Math.min(Number(url.searchParams.get("limit") || 200), 500);
      const rawRecords = readDialog(0); // 0 = 全量（配合 since/before 游标；缓存已让它不贵）
      const all = applyClaimStates(rawRecords.map(normalizeRecordNames));
      const withAcks = applyNoticeAcks(all);
      // ── 游标（为 App 准备的增量同步）──────────────────────────────
      //   不带参数：最后 limit 条（老行为，页面照旧）
      //   ?since=<id>：这条**之后**的新记录（增量拉取）
      //   ?before=<id>：这条**之前**的 limit 条（往回翻历史）
      const convAll = withAcks.filter((r) => r.kind !== "progress");
      const sinceId = String(url.searchParams.get("since") || "").trim();
      const beforeId = String(url.searchParams.get("before") || "").trim();
      let conv = convAll;
      if (sinceId) {
        const i = convAll.findIndex((r) => String(r.id) === sinceId);
        conv = i >= 0 ? convAll.slice(i + 1).slice(0, limit) : convAll.slice(-limit);
      } else if (beforeId) {
        const i = convAll.findIndex((r) => String(r.id) === beforeId);
        conv = i > 0 ? convAll.slice(Math.max(0, i - limit), i) : [];
      } else {
        conv = convAll.slice(-limit);
      }
      const prog = withAcks.filter((r) => r.kind === "progress").slice(-40);
      const oldest = convAll.length ? String(convAll[0].id) : "";
      const newest = convAll.length ? String(convAll[convAll.length - 1].id) : "";
      const nextBefore = conv.length ? String(conv[0].id) : "";
      const records = conv.concat(prog).sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
      const addedMembers = registerMembers(all); // 新成员自己长出来
      const cfg = readAgents();
      const agents = Object.entries(cfg.agents || {}).map(([alias, meta]) => {
        // "本尊上次发言"要**排除代答**（代答是程序顶着本线名发的）→ 统一走 lastOwnStatementTs，
        // 与 /api/contacts、/api/employees、页面芯片同一个口径，不再各写一遍。
        const lastSeen = lastOwnStatementTs(alias, all);
        const open = all.filter((r) => {
          if (String(r.to || "").toLowerCase() !== alias) return false;
          if (String(r.from || "").toLowerCase() === alias) return false;
          if (r.kind === "progress") return false;
          return r.state !== "done" && r.state !== "failed";
        }).length;
        // 状态自动维护：不靠人改 status 字段，按“最近一次发言”现算
        const ageMs = lastSeen ? Date.now() - parseCst(lastSeen) : null;
        const health = ageMs == null ? "none" : ageMs < 3 * 3600e3 ? "active" : ageMs < 24 * 3600e3 ? "idle" : "stale";
        return {
          alias,
          label: meta.label || alias,
          title: meta.title || "",
          workspace: meta.workspace || "",
          // 退役的线：status 直接写 retired（与 /api/contacts 一致），页面据此灰显 + 写「退役」
          status: String(meta.status || "").toLowerCase() === "retired" ? "retired" : health,
          retired: String(meta.status || "").toLowerCase() === "retired",
          note: normalizeTaskIds(meta.note || ""),
          auto: !!meta.auto,
          lastSeen,
          idleMin: ageMs == null ? null : Math.round(ageMs / 60000),
          open,
          pendingMail: pendingMailFor(alias, lastSeen),    // 真未读（比本人上次发言新）；退役条目不叫不计
          duty: dutyEnabled(alias),                        // 这条线有没有值守（老板要求"开关状态可见"）
          avatar: avatarOf(alias),                          // 头像（稳定派生：首字 + 色相）
        };
      });
      sendJson(res, 200, {
        records,
        cursor: { oldestId: oldest, newestId: newest, nextBefore: nextBefore, total: convAll.length, hasMore: !!nextBefore && nextBefore !== oldest },
        conversationCount: conv.length,
        progressCount: prog.length,
        claimTimeoutMs: CLAIM_TIMEOUT_MS,
        agents,
        addedMembers,
        groups: listGroups().map((g) => ({ ...g, avatar: avatarOf(g.name) })), // HUB-010：顶部群组
        halt: readHalt(), // HUB-006：暂停闸状态（页面据此显示红条/绿条）
        // HUB-003：置顶「待老板：N 条」。muted 只是"别打扰"，事件仍在 items 里（不丢）
        boss: (() => {
          const evs = readBossEvents();
          const pend = bossPending(evs, all);
          return {
            count: pend.length,
            muted: !!readState().bossMuted,
            today: bossTodayCount(evs),
            limit: BOSS_DAILY_MAX,
            items: pend.slice(-8).map((e) => ({
              ts: e.ts,
              from: e.from,
              kind: e.kind,
              kindLabel: BOSS_KINDS[e.kind] || e.kind,
              task: e.task || "",
              needAction: e.needAction || "",
            })),
            // 诚实口径：页面内提醒只在你开着页面时有效；系统推送是将来项（见 HUB-003 卡）
            note: "页面内提醒只在你开着本页面时有效；系统推送列为将来项（HUB-003）",
          };
        })(),
        nameViolations: auditNames(rawRecords),
        nameAuditSince: toCst(new Date(NAME_AUDIT_SINCE)),
        updatedAt: fmtNow(),
      });
      return;
    }

    if (req.method === "POST" && (url.pathname === "/api/board" || url.pathname === "/api/send")) {
      let payload;
      try {
        payload = JSON.parse((await readBody(req)) || "{}");
      } catch {
        sendJson(res, 400, { error: "格式不对" });
        return;
      }
      const message = String(payload.message || "").trim();
      let target = String(payload.target || "codex-看板服务").trim().replace(/^@/, "");
      // 署名：默认"老板"（手机是你本人在用）；程序/别的线代发时可以显式给 author，
      // **必须是注册看板名**，不许借名（HUB-004 四之二 + 总监 05:24 实测的落款缺口）。
      const rawAuthor = String(payload.author || "").trim().replace(/^@/, "");
      let sender = "老板";
      if (rawAuthor) {
        const names2 = Object.keys(readAgents().agents || {});
        const hit = names2.find((n) => n.toLowerCase() === rawAuthor.toLowerCase()) ||
          names2.find((n) => String((readAgents().agents[n] || {}).slug || "").toLowerCase() === rawAuthor.toLowerCase()) ||
          (boardName(rawAuthor) !== rawAuthor ? boardName(rawAuthor) : "");
        if (!hit || !names2.includes(hit)) {
          sendJson(res, 400, { error: "author 没注册：" + rawAuthor, hint: names2.join("、") });
          return;
        }
        sender = hit;
      }
      const mm = message.match(/^@([A-Za-z0-9_\u4e00-\u9fa5-]{1,32})/);
      if (mm) target = mm[1];
      if (!/^[A-Za-z0-9_\u4e00-\u9fa5-]{1,32}$/.test(target)) {
        sendJson(res, 400, { error: "收件人不合法" });
        return;
      }
      // 新写的行一律用看板名当 @句柄（旧句柄照样接受，只是不再新写出去）
      target = boardName(target);
      // HUB-013：旧工号不再可投递（岗位名延续、工号换代）
      const ro = retiredSlugOwner(target);
      if (ro) {
        sendJson(res, 400, {
          error: "这是**退役工号**，不再投递：" + target,
          hint: "请用岗位名 @" + ro + "（同名即现任）",
        });
        return;
      }
      if (!message || message.length > 4000) {
        sendJson(res, 400, { error: "消息不能为空且不超过 4000 字" });
        return;
      }
      // 引用回复：把被引用的那条记录挂到新记录的 refs.quote 上，并在看板行里带上人读得懂的引用头
      const quoteId = String(payload.quoteId || "").trim();
      let quoteRefs = null;
      let content = message;
      if (quoteId) {
        const src = readDialog(500).find((x) => x.id === quoteId);
        if (src) {
          quoteRefs = {
            id: src.id,
            ts: src.ts,
            from: src.from,
            to: src.to,
            kind: src.kind,
            channel: src.channel,
            body: clip(src.body, 120),
          };
          content =
            "↩ 回复 " + String(src.from || "") + " " + String(src.ts || "").slice(5, 16).replace("T", " ") +
            "：「" + clip(src.body, 50) + "」\n" + message;
        }
      }
      appendBoardLine(target, sender, content, quoteRefs ? { quote: quoteRefs } : null);
      scheduleCheck();
      sendJson(res, 200, { ok: true });
      return;
    }

    sendJson(res, 404, { error: "not found" });
  });

  server.requestTimeout = 0;
  server.headersTimeout = 0;
  // keepAliveTimeout 必须是“正常值”（Node 默认 5000），不能用 60000：
  // 实测（2026-09-10 CT-003 复核）只要把它设成 60000，空闲 3 秒后的第一个请求会卡 ~25-29 秒才到服务端
  // （同一份代码只改这一个值即可复现/消除；手机页每 5 秒轮询、发消息也会卡在“发送中…”）。
  // 别的两项（requestTimeout/headersTimeout = 0）单独测过没有这个问题，保持不动。
  server.keepAliveTimeout = 5000;

  try {
    fs.watch(path.dirname(BOARD_FILE), (event, filename) => {
      if (filename && filename.toLowerCase() === path.basename(BOARD_FILE).toLowerCase()) {
        scheduleCheck();
      }
    });
  } catch (e) {
    log("WATCH DIR FAILED:", e.message);
  }
  fs.watchFile(BOARD_FILE, { interval: 5000 }, () => scheduleCheck());
  fs.watchFile(PROGRESS_FILE, { interval: 3000 }, () => ingestProgress());
  watcherReady = true;

  checkTimeline();
  setInterval(checkTimeline, 20000);
  log("DISPATCH LOOP STARTED events=" + WATCH_EVENTS.length);
  // 值守分线：盯着本线信箱（本尊不在时替它回话）
  setInterval(() => {
    dutyTick().catch((e) => log("DUTY TICK FAILED:", e.message));
  }, DUTY.pollMs);
  log("DUTY LOOP STARTED alias=" + DUTY.alias + " poll=" + DUTY.pollMs + "ms");
  // HUB-002 忙等门铃：退避到点后补投一次（一轮只补一条线；仍进不去就再退避）
  setInterval(() => {
    wakeRetryTick().catch((e) => log("WAKE RETRY TICK FAILED:", e.message));
  }, WAKE_RETRY_MS);
  log("WAKE RETRY LOOP STARTED poll=" + WAKE_RETRY_MS + "ms backoff=" + WAKE_BACKOFF_MS.join("/") + "ms");
  // HUB-006：暂停期间每 30 分钟在看板重申一次（节流；标"重复提醒"），直到解除
  setInterval(() => {
    try {
      const h = readHalt();
      if (!h.halted) return;
      if (Date.now() - Number(h.lastRemindAt || 0) < HALT_REPEAT_MS) return;
      writeHalt({ ...h, lastRemindAt: Date.now() });
      appendBoardLine("老板", CODEX_SERVICE,
        "【已暂停 · 重复提醒】" + (h.reason || "（未写原因）") +
        " · 仍在等你：处理完发 `@全体 【解除暂停】…` 即可恢复。");
      log("HALT REMIND REPEATED");
    } catch (e) {
      log("HALT REMIND FAILED:", e.message);
    }
  }, 60000);
  log("HALT REMINDER LOOP STARTED every=" + Math.round(HALT_REPEAT_MS / 60000) + "min");
  // 公告催办（"必须回复收到"）：每 10 分钟扫一次未回执的线
  setInterval(() => {
    noticeNudgeTick().catch((e) => log("NOTICE NUDGE TICK FAILED:", e.message));
  }, 600000);
  log("NOTICE NUDGE LOOP STARTED every=10min max=" + NOTICE_NUDGE_MAX);
  // 署名违规自动提醒（每个泛称 6 小时一次，只投信箱不写看板）
  nameReminderTick();
  setInterval(nameReminderTick, 300000);
  log("NAME REMINDER LOOP STARTED (5min)");

  function startListening() {
    server.once("error", (err) => {
      log("LISTEN ERROR:", err.message, "-> 15s 后重试（常见于开机时 Tailscale 尚未就绪）");
      setTimeout(startListening, 15000);
    });
    server.listen(PORT, HOST, () => {
      log("BOARD LISTENING on http://" + HOST + ":" + PORT);
      log("BOARD_FILE=" + BOARD_FILE);
    });
  }
  startListening();

  const stop = () => {
    if (shuttingDown) return;
    shuttingDown = true;
    log("Shutting down board service...");
    try {
      server.close(() => process.exit(0));
    } catch {}
    setTimeout(() => process.exit(0), 2000).unref();
  };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
}

main().catch((e) => {
  process.stderr.write("FATAL " + e.stack + "\n");
  process.exit(1);
});
