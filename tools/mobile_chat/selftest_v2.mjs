// 会话工具 v2 自测：全渠道入 Hub（inbox 任务 + 桥信箱）+ 接单锁状态机
//
// 做法：把 board.mjs 拉起来跑在**完全隔离的临时目录**里（看板/inbox/桥信箱/dialog 数据全部指向
// 临时路径，端口 8799 绑 127.0.0.1），喂已知时间线的一组夹具，然后断言 /api/dialog 里的归一
// 记录与状态。全程不动仓库里的运行态数据。
//
// 用法：node tools/mobile_chat/selftest_v2.mjs [--tmp <目录>]
//   --tmp：指定临时根目录（跨环境一致性用）。默认**项目内** run/selftest-tmp，
//          不再默认用系统 TEMP —— 见下面关于 libuv fs.watch 短名崩溃的说明。

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import vm from "node:vm";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BOARD_MJS = path.join(__dirname, "board.mjs");
// 端口随机取一段，避免上一次异常退出残留的实例占着固定端口（顺带也就不会误连到别人的服务）
const PORT = Number(process.env.SELFTEST_PORT || (8800 + Math.floor(Math.random() * 90)));
const HOST = "127.0.0.1";
const TIMEOUT_MS = 5 * 60 * 1000;
// Windows 的 libuv fs.watch 有个坑（src\win\fs-event.c:72 断言崩溃 → "临时服务起不来"的偶发失败）：
// 只要**监听目录本身带 8.3 短名别名**（`C:\Users\ADMINI~1\...` 这类），事件里的文件名和监听
// 路径就对不上，直接断言失败。**2026-09-13 补**：`fs.realpathSync()`（JS 版）**不展开** 8.3 短名，
// 必须用 `fs.realpathSync.native()`（走 GetFinalPathNameByHandle）才拿得到长名——这也解释了
// codex-总监 那边为什么会在门禁里崩（他跑的两遍都挂在同一个断言上）。
// 三道一起用：
//   ① 临时根目录**默认放项目内** `run/selftest-tmp`（躲开 %TEMP% 的短名/权限差异），可用 `--tmp` 改；
//   ② 拿到长名再往下拼（native realpath，拿不到就退回原值）；
//   ③ 每轮的子目录名保持 8.3 兼容（≤8 字符）。
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const tmpArgIdx = process.argv.indexOf("--tmp");
const TMP_BASE = path.resolve(
  (tmpArgIdx >= 0 && process.argv[tmpArgIdx + 1]) || process.env.SELFTEST_TMP || path.join(REPO_ROOT, "run", "selftest-tmp")
);
function longPath(p) {
  try {
    fs.mkdirSync(p, { recursive: true });
    return fs.realpathSync.native(p);
  } catch {
    try { return fs.realpathSync(p); } catch { return p; }
  }
}
// 让 run/ 永远不出现在 git status 里（不碰共享的 .gitignore：那里压着别人未提交的改动）
try {
  const baseDir = path.dirname(TMP_BASE);
  fs.mkdirSync(baseDir, { recursive: true }); // 先建目录：否则写 .gitignore 会 ENOENT 被吞掉（踩过）
  const gi = path.join(baseDir, ".gitignore");
  if (!fs.existsSync(gi)) fs.writeFileSync(gi, "*\n", "utf8");
} catch {}
const ROOT = path.join(longPath(TMP_BASE), "ct2" + Date.now().toString(36).slice(-4));

const pad = (n) => String(n).padStart(2, "0");
function cst(date) {
  const d = new Date(date.getTime() + 8 * 3600 * 1000);
  return (
    d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()) +
    "T" + pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()) + ":" + pad(d.getUTCSeconds()) + "+08:00"
  );
}
function boardStamp(date) {
  const s = cst(date);
  return s.slice(0, 10) + " " + s.slice(11, 16);
}
function boardTimeOnly(date) {
  return cst(date).slice(11, 16);
}

const NOW = Date.now();
const MIN = 60 * 1000;
const T = {
  reply: new Date(NOW - 30 * MIN), // 看板里 DSH-main 的回帖
  overdue: new Date(NOW - 10 * MIN), // 派单在回帖之后 + 超时 => 待办
  cleared: new Date(NOW - 60 * MIN), // 派单在回帖之前 => 回复自动消
  fresh: new Date(NOW - 10 * 1000), // 刚派单 => 已派单待回
  bridge: new Date(NOW - 3 * 60 * MIN),
};

const dirs = {
  data: path.join(ROOT, "data"),
  inbox: path.join(ROOT, "inbox"),
  inboxDone: path.join(ROOT, "inbox", "done"),
  bridge: path.join(ROOT, "bridge"),
  bridgeMessages: path.join(ROOT, "bridge", "messages"),
  bridgeTasks: path.join(ROOT, "bridge", "tasks"),
  mailbox: path.join(ROOT, "mailbox"),
  tasks: path.join(ROOT, "tasks"),
  locks: path.join(ROOT, "locks"),
  stub: path.join(ROOT, "stub"),
};
const BOARD_FILE = path.join(ROOT, "COMMS_BOARD.md");
const DIALOG_FILE = path.join(ROOT, "dialog.ndjson");
const AGENTS_FILE = path.join(ROOT, "agents.json");

const results = [];
const T0 = Date.now();
const el = () => "+" + ((Date.now() - T0) / 1000).toFixed(1) + "s";
const trace = (label) => process.stdout.write("[" + el() + "]   · " + label + "\n");
async function timed(label, fn) {
  const t = Date.now();
  const v = await fn();
  trace(label + " 耗时 " + ((Date.now() - t) / 1000).toFixed(1) + "s");
  return v;
}
function check(name, ok, detail) {
  results.push({ name, ok: !!ok, detail: detail || "" });
  process.stdout.write("[" + el() + "] " + (ok ? "  PASS  " : "  FAIL  ") + name + (detail ? "  -> " + detail : "") + "\n");
}

function setup() {
  for (const d of Object.values(dirs)) fs.mkdirSync(d, { recursive: true });
  // Codex CLI 桩程序（自测专用，MCHAT_CODEX_BIN 指向它）：
  //   - 线程号里有 01a0dddd 的那条线 → 写回复文件、退出 0（模拟"被正常唤醒并回话"）
  //   - 其它线程号 → 回一句抢锁冲突、退出 1（模拟"桌面端占着写锁"）
  // 有了它，自测能真的走完"注入 → 回话落看板"，而**不必去碰真会话**。
  fs.writeFileSync(
    path.join(dirs.stub, "codex-stub.cmd"),
    [
      "@echo off",
      "setlocal",
      'echo %* | findstr /C:"queue" >nul',
      "if errorlevel 1 goto resume",
      "rem ---- queue 模式：只有 01a0dddd 那条线排队成功 ----",
      'echo %* | findstr /C:"01a0dddd" >nul',
      "if errorlevel 1 goto lockerr",
      "exit /b 0",
      ":resume",
      "rem ---- resume 模式：01a0dddd 成功；01a01111 只有 resume 能成（用来验备用路径） ----",
      'echo %* | findstr /C:"01a0dddd" >nul',
      "if errorlevel 1 goto resume2",
      'echo selftest stub reply>"%MCHAT_DATA%\\last_board.txt"',
      "exit /b 0",
      ":resume2",
      'echo %* | findstr /C:"01a01111" >nul',
      "if errorlevel 1 goto lockerr",
      'echo selftest stub resume reply>"%MCHAT_DATA%\\last_board.txt"',
      "exit /b 0",
      ":lockerr",
      "echo thread-store conflict: already has an active writer 1>&2",
      "exit /b 1",
      "",
    ].join("\r\n"),
    "utf8"
  );
  fs.writeFileSync(BOARD_FILE, ["# 自测看板（临时）", "", "- @老板 " + boardStamp(T.reply) + " DSH-main：收到", ""].join("\n"), "utf8");
  fs.writeFileSync(DIALOG_FILE, "", "utf8");
  // 闲置会话停用清单的夹具：codex-测占用2 的会话标成"停用"，验证投递口会绕开它
  fs.writeFileSync(
    path.join(dirs.data, "state.json"),
    JSON.stringify({ retiredThreads: { "01a0ffff-0000-7000-8000-000000000005": { why: "自测：已停用", by: "自测" } } }, null, 2),
    "utf8"
  );
  // 任务卡夹具（HUB-008）：两张卡，用来验证"卡 + 派单 → 一张任务表"
  fs.writeFileSync(
    path.join(dirs.tasks, "HUB-901.md"),
    ["# HUB-901 夹具卡甲（自测）", "", "- 派单人：老板　接手：`codex-看板编辑`", "- **类型**：`dev`　**优先级**：`P1`", "", "## 二、验收标准（逐条可判定）", "", "1. 甲", ""].join("\n"),
    "utf8"
  );
  fs.writeFileSync(
    path.join(dirs.tasks, "KIT-901.md"),
    ["# KIT-901 夹具卡乙（自测）", "", "- 派单人：老板　接手：`codex-套件`", "- **类型**：`test`　**优先级**：`P2`", ""].join("\n"),
    "utf8"
  );
  // 故意写一份“旧 schema + 手工成员”的实例表：验证迁移时只合并不覆盖
  fs.writeFileSync(
    AGENTS_FILE,
    JSON.stringify(
      {
        schema: 1,
        primary: "dsh-main",
        agents: {
          "codex-手工成员": { label: "codex-手工成员", title: "手工", slug: "codex-manual", note: "自测：手工条目必须活下来" },
          codex: { label: "Codex", workspace: "x" },
          // HUB-002 判定用的三条夹具线（在岗 / 退役 / 没绑定会话）
          "codex-测在岗": { label: "codex-测在岗", title: "自测", slug: "codex-awake", threadId: "01a0aaaa-0000-7000-8000-000000000001", status: "active" },
          "codex-测退役": { label: "codex-测退役", title: "自测", slug: "codex-retired", status: "retired" },
          "codex-测未上岗": { label: "codex-测未上岗", title: "自测", slug: "codex-noone", status: "unknown" },
          // 忙线：**故意不给 threadId** —— 就算判忙规则被改坏，最坏也只是走到 duty，绝不会真去注入
          "codex-测忙": { label: "codex-测忙", title: "自测", slug: "codex-mtest", status: "busy" },
          // 特批 must-fix 用：窗口占用（有锁文件）但空闲 / 抢锁失败
          "codex-测窗口": { label: "codex-测窗口", title: "自测", slug: "codex-awake2", threadId: "01a0dddd-0000-7000-8000-000000000003", status: "active" },
          // 关掉值守：专门验证"无值守时才 park + 标注已投递未唤醒"
          "codex-测占用": { label: "codex-测占用", title: "自测", slug: "codex-occ", threadId: "01a0eeee-0000-7000-8000-000000000004", status: "active", duty: false },
          // 有值守：窗口占用时应交给它自己的值守，而不是 park
          "codex-测占用2": { label: "codex-测占用2", title: "自测", slug: "codex-occ2", threadId: "01a0ffff-0000-7000-8000-000000000005", status: "active" },
          // REQ-HUB-004b：queue 失败但 resume 能成 → 验证"备用路径"
          "codex-测备用": { label: "codex-测备用", title: "自测", slug: "codex-backup", threadId: "01a01111-0000-7000-8000-000000000006", status: "active" },
          // 没有绑定会话、但状态在岗：用来验证"服务不冒充那条线说话"
          // 没有会话的"真·空席位"：代答只给它（有本尊的线默认不代答，见 dutyEnabled）
          "codex-测无会话": { label: "codex-测无会话", title: "自测", slug: "codex-nosession", status: "active" },
          // "未读口径"专用线（总监 2026-09-12 22:24 正式请求的回归）
          "codex-测未读": { label: "codex-测未读", title: "自测", slug: "codex-unread", status: "active" },
          // 显式关掉值守：用来验证"无值守时只发服务自己署名的系统事实"
          "codex-测无值守": { label: "codex-测无值守", title: "自测", slug: "codex-noduty", status: "active", duty: false },
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const task = (name, ts, extra) =>
    fs.writeFileSync(
      path.join(dirs.inbox, name),
      JSON.stringify(
        {
          schema: "dialog.v1",
          to: "dsh",
          instance: "dsh-main",
          claimedBy: "dsh-main",
          state: "dispatched",
          from: "codex",
          target: "selftest",
          ts: cst(ts),
          do: "自测夹具：" + name,
          why: "selftest",
          accept: false,
          ...(extra || {}),
        },
        null,
        2
      ),
      "utf8"
    );

  task("selftest_overdue.task.json", T.overdue);
  task("selftest_cleared_by_reply.task.json", T.cleared);
  task("selftest_dispatched_fresh.task.json", T.fresh);
  // 改号夹具：正文里故意写旧号，验证**读取时**归一成新号（落盘原文不动）
  task("selftest_taskid_alias.task.json", T.fresh, { do: "自测夹具：改号 CT-021 与 CT-022 在界面上应显示成 HUB-001 / HUB-002" });
  fs.writeFileSync(
    path.join(dirs.inboxDone, "selftest_archived.task.json"),
    JSON.stringify({ schema: "dialog.v1", to: "dsh", instance: "dsh-main", claimedBy: "dsh-main", ts: cst(T.cleared), do: "自测夹具：已归档" }, null, 2),
    "utf8"
  );

  fs.writeFileSync(
    path.join(dirs.bridgeMessages, "11111111-1111-1111-1111-111111111111.json"),
    JSON.stringify({ id: "11111111-1111-1111-1111-111111111111", sender: "dsh", recipient: "codex", kind: "milestone", body: "自测：桥消息（发给 Codex、未读、已超时）", progress: "p", evidence: "e", createdAt: new Date(T.bridge).toISOString(), readAt: null }, null, 2),
    "utf8"
  );
  fs.writeFileSync(
    path.join(dirs.bridgeMessages, "22222222-2222-2222-2222-222222222222.json"),
    JSON.stringify({ id: "22222222-2222-2222-2222-222222222222", sender: "codex", recipient: "dsh", kind: "reply", body: "自测：桥消息（Codex 发出）", createdAt: new Date(T.bridge).toISOString(), readAt: null }, null, 2),
    "utf8"
  );
  fs.writeFileSync(
    path.join(dirs.bridgeTasks, "33333333-3333-3333-3333-333333333333.json"),
    JSON.stringify({ taskId: "33333333-3333-3333-3333-333333333333", rootTaskId: "33333333-3333-3333-3333-333333333333", owner: "dsh", status: "running", objective: "自测：桥任务（running）", createdAt: new Date(T.bridge).toISOString() }, null, 2),
    "utf8"
  );
  fs.writeFileSync(
    path.join(dirs.bridgeTasks, "44444444-4444-4444-4444-444444444444.json"),
    JSON.stringify({ taskId: "44444444-4444-4444-4444-444444444444", rootTaskId: "44444444-4444-4444-4444-444444444444", owner: "dsh", status: "completed", objective: "自测：桥任务（completed）", createdAt: new Date(T.bridge).toISOString() }, null, 2),
    "utf8"
  );
}

async function waitFor(fn, ms) {
  const until = Date.now() + ms;
  for (;;) {
    try {
      const v = await fn();
      if (v) return v;
    } catch {}
    if (Date.now() > until) return null;
    await new Promise((r) => setTimeout(r, 300));
  }
}

// —————————— 页面内联 JS：长按 @提及（从 board.mjs 里“取源码来跑”，不是抄一份） ——————————

function pageJs() {
  const s = fs.readFileSync(BOARD_MJS, "utf8");
  // 页面里现在有两个 <script>：第一个是"版本守卫"，主脚本在最后一个。
  const i = s.lastIndexOf("<script>");
  const j = s.lastIndexOf("</script>");
  return s.slice(i + 8, j);
}

// 按名字从源码里摘出整个函数（大括号配平；这几个函数里的花括号都在配平的位置）
function grabFunction(js, name) {
  const start = js.indexOf("function " + name + "(");
  if (start < 0) throw new Error("页面 JS 里找不到函数：" + name);
  let depth = 0;
  for (let i = js.indexOf("{", start); i < js.length; i++) {
    if (js[i] === "{") depth++;
    else if (js[i] === "}") {
      depth--;
      if (depth === 0) return js.slice(start, i + 1);
    }
  }
  throw new Error("函数大括号不配平：" + name);
}

function fakeEl() {
  const handlers = {};
  return {
    style: {},
    dataset: {},
    textContent: "",
    addEventListener(t, f) {
      (handlers[t] = handlers[t] || []).push(f);
    },
    dispatch(t, e) {
      for (const f of handlers[t] || []) f(e || { preventDefault() {} });
    },
    has(t) {
      return !!(handlers[t] || []).length;
    },
  };
}

// —————————— 整页脚本冒烟 ——————————
// 把**完整**的页面 JS 在一套最小 DOM 桩上跑一遍。专抓"HTML 正常但脚本初始化就抛错"这类
// 线下看不出来、线上表现为"只剩一个顶栏和输入框、点不动"的坑（2026-09-10 真出现过）。
function stubEl(tag) {
  const cls = new Set();
  const el = {
    tag,
    style: {},
    dataset: {},
    children: [],
    value: "",
    textContent: "",
    selected: false,
    height: 0,
    scrollHeight: 1000,
    scrollTop: 0,
    clientHeight: 600,
    classList: {
      add: (c) => cls.add(c),
      remove: (c) => cls.delete(c),
      toggle: (c, on) => {
        const v = on === undefined ? !cls.has(c) : !!on;
        v ? cls.add(c) : cls.delete(c);
        return v;
      },
      contains: (c) => cls.has(c),
    },
    addEventListener() {},
    appendChild(c) {
      this.children.push(c);
      return c;
    },
    insertBefore() {},
    removeChild() {},
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    focus() {},
    closest() {
      return null;
    },
    setAttribute() {},
    getAttribute() {
      return null;
    },
    scrollIntoView() {},
  };
  Object.defineProperty(el, "innerHTML", {
    get() {
      return "";
    },
    set() {
      el.children.length = 0;
    },
  });
  return el;
}

// 线上页面（渲染后的真实产物）内联脚本语法检查。
// 教训：board.mjs 里 PAGE 是**模板字符串**，源码里的 "\n" / "\s" 会被 Node 转义掉，
// 到浏览器就变成"字符串没闭合"→整段脚本语法错→页面只剩顶栏和输入框。
// 所以必须查**渲染结果**，只 node --check 模板源码是查不出来的。
function testServedPageSyntax(html) {
  const src = String(html || "");
  const scripts = [...src.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
  check("线上页面：确有内联脚本可查", scripts.length >= 1, scripts.length + " 个");
  let bad = null;
  for (let i = 0; i < scripts.length; i++) {
    try {
      new vm.Script(scripts[i]);
    } catch (e) {
      bad = "第" + (i + 1) + "个 <script>：" + e.message;
    }
  }
  check("线上页面：内联脚本语法正确（按渲染结果检查，而非模板源码）", !bad, bad || scripts.length + " 个脚本全部通过");
}

// 从**渲染后的页面**里取主脚本（最后一个 <script>）。页面测试一律用它，
// 而不是 board.mjs 里的模板源码——两者在转义上可能不一样（这正是 2026-09-10 那次事故）。
function servedPageJs(html) {
  const scripts = [...String(html || "").matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
  return scripts[scripts.length - 1] || "";
}

function testPageRender(records, js) {
  const els = new Map();
  const getEl = (sel) => {
    if (!els.has(sel)) els.set(sel, stubEl(sel));
    return els.get(sel);
  };
  const boardEl = getEl("#board");
  const store = {};
  const sandbox = {
    console,
    addEventListener() {},
    document: {
      hidden: false,
      body: stubEl("body"),
      addEventListener() {},
      querySelector: (sel) => getEl(sel),
      querySelectorAll: () => [],
      createElement: (t) => stubEl(t),
      createTextNode: (t) => ({ text: t }),
    },
    location: { search: "", href: "", reload() {} },
    URLSearchParams,
    localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => (store[k] = String(v)) },
    setTimeout: () => 0,
    clearTimeout: () => {},
    setInterval: () => 0,
    fetch: () =>
      Promise.resolve({
        status: 200,
        json: () =>
          Promise.resolve({
            records: [],
            agents: [],
            ok: true,
            ver: "x",
            updatedAt: "x",
            nameViolations: [],
            addedMembers: [],
          }),
      }),
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);

  let initErr = null;
  try {
    vm.runInContext(
      js + "\nglobalThis.__page={renderDialog,renderAgents,renderWarn,syncTools,setPanel,updateJump,atBottom,searchHits,renderSearch,renderBody,taskLineText};",
      sandbox
    );
  } catch (e) {
    initErr = e;
  }
  check("页面脚本：能在最小 DOM 上跑完初始化（不抛异常）", !initErr, initErr ? String(initErr.message) : "ok");
  if (initErr) return;

  const p = sandbox.__page;
  let renderErr = null;
  try {
    p.renderDialog(records);
  } catch (e) {
    renderErr = e;
  }
  check("页面渲染：真实数据渲染不抛异常", !renderErr, renderErr ? String(renderErr.message) : "ok");
  if (renderErr) return;
  check("页面渲染：渲染后消息区确实有内容", boardEl.children.length > 0, "children=" + boardEl.children.length);
  let searchErr = null;
  try {
    p.renderSearch("dsh");
  } catch (e) {
    searchErr = e;
  }
  check("页面搜索：渲染结果不抛异常", !searchErr, searchErr ? String(searchErr.message) : "ok");

  // 代码 / 纯文字 区分：围栏代码块 -> <pre class=code>，行内反引号 -> <code class=ic>
  const body = stubEl("div");
  const BT = String.fromCharCode(96); // 反引号，避免在这份文件里写出来
  p.renderBody(body, "看这段：" + BT + BT + BT + "js\nconst a = 1;\n" + BT + BT + BT + "\n还有 " + BT + "node --check" + BT + " 这种。");
  const pres = body.children.filter((c) => c.tag === "pre" && c.className === "code");
  const ics = body.children.filter((c) => c.tag === "code" && c.className === "ic");
  check("正文区分：围栏代码块渲染成 <pre class=code>", pres.length === 1, "pre=" + pres.length);
  check("正文区分：行内反引号渲染成 <code class=ic>", ics.length === 1, "ic=" + ics.length);
  check("正文区分：纯文字保持文本节点（不被当代码）", body.children.some((c) => c.tag === undefined && typeof c.text === "string"), body.children.length + " 个节点");

  // 每种记录类型都要能渲染（2026-09-11 教训：公告分支写错变量名 refs/rf，
  // 只在有公告的记录上才炸，而夹具里没有公告 → 自测漏过，线上白屏）
  const kinds = [
    { id: "k1", ts: "2026-09-11T02:00:00+08:00", from: "老板", to: "codex-看板服务", channel: "board", kind: "message", body: "普通消息", state: "done" },
    { id: "k2", ts: "2026-09-11T02:01:00+08:00", from: "老板", to: "全体", channel: "board", kind: "notice", body: "公告正文", state: "done",
      refs: { active: true, expected: ["dsh-老员工", "codex-看板编辑"], acks: { "dsh-老员工": { ts: "2026-09-11T02:05:00+08:00", mode: "point" } } } },
    { id: "k3", ts: "2026-09-11T02:02:00+08:00", from: "老板", to: "全体", channel: "board", kind: "notice", body: "过期公告", state: "done",
      refs: { active: false, expired: true, expected: ["dsh-老员工"], acks: {} } },
    { id: "k4", ts: "2026-09-11T02:03:00+08:00", from: "codex-看板服务", to: "dsh-老员工", channel: "inbox", kind: "task", body: "派单正文", state: "dispatched", overdue: true, refs: { inbox: "x.task.json", instance: "dsh-老员工" } },
    { id: "k5", ts: "2026-09-11T02:04:00+08:00", from: "dsh-quant", to: "none", channel: "bridge", kind: "progress", body: "英文进度 reasoning", state: "done" },
  ];
  let kindsErr = null;
  try {
    p.renderDialog(kinds);
  } catch (e) {
    kindsErr = e;
  }
  check("页面渲染：五种记录类型都能渲染（消息/公告/过期公告/派单/进度）", !kindsErr, kindsErr ? String(kindsErr.message) : "ok");
  check("页面渲染：公告卡片确实生成", boardEl.children.filter((c) => String(c.className).indexOf("notice") >= 0).length >= 1, "notice=" + boardEl.children.filter((c) => String(c.className).indexOf("notice") >= 0).length);
}

function testPageMention(js) {
  // `lvlOf` / `isMemberNoise`：HUB-018 B（老板面剔除组员↔组长往来）的判据函数——**必须能单独抽出来验**，
  //   否则这条产品口径只能靠肉眼在真页面上看，没回归保护。
  const fns = ["mentionPrefixOf", "knownTargets", "effectiveTarget", "renderTargets", "setTarget", "insertMention", "addLongPress", "lpSuppressClick", "refreshRouteHint", "violAck", "freshViolations", "lvlOf", "isMemberNoise"];
  const src =
    'function $(s){return document.querySelector(s);}\n' +
    "function toast(t){globalThis.__toasts.push(t);}\n" +
    fns.map((n) => grabFunction(js, n)).join("\n") +
    "\nglobalThis.__lp={insertMention,addLongPress,lpSuppressClick,refreshRouteHint,mentionPrefixOf,knownTargets,effectiveTarget,setTarget,renderTargets,violAck,freshViolations,lvlOf,isMemberNoise};";

  const msgEl = { value: "", focus() {}, addEventListener() {} };
  const statusEl = { textContent: "" };
  const routeHint = { style: { display: "none" }, textContent: "" };
  const classes = new Set();
  const targetSel = {
    style: {},
    dataset: {},
    value: "",
    innerHTML: "",
    options: [],
    classList: { toggle(c, on) { if (on) classes.add(c); else classes.delete(c); }, contains: (c) => classes.has(c) },
    appendChild(o) { this.options.push(o); },
    addEventListener() {},
  };
  const doc = {
    querySelector(sel) {
      if (sel === "#routeHint") return routeHint;
      if (sel === "#targetSel") return targetSel;
      return null;
    },
    createElement() {
      return { value: "", textContent: "", selected: false };
    },
  };
  const timers = [];
  let clock = 1000;
  const sandbox = {
    msgEl,
    statusEl,
    document: doc,
    QUOTE: null,
    TARGET: "codex-看板服务",
    // 级别字段是 HUB-018 B 的判据来源（真实页面从 /api/dialog 的 agents[] 取，同一份名册）
    AGENTS: [
      { alias: "dsh-老员工", level: "member" },
      { alias: "dsh-quant", level: "member" },
      { alias: "codex-看板服务", level: "lead" },
      { alias: "codex-看板编辑", level: "lead" },
      { alias: "codex-总监", level: "director" },
    ],
    localStorage: (() => {
      const store = {};
      return {
        getItem: (k) => (k in store ? store[k] : null),
        setItem: (k, v) => {
          store[k] = String(v);
        },
      };
    })(),
    Date: { now: () => clock },
    setTimeout: (fn, ms) => {
      timers.push({ fn, ms, dead: false });
      return timers.length;
    },
    clearTimeout: (id) => {
      if (timers[id - 1]) timers[id - 1].dead = true;
    },
    console,
  };
  sandbox.globalThis = sandbox;
  sandbox.__toasts = [];
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  const runTimers = () => {
    for (const t of timers) {
      if (!t.dead) {
        t.dead = true;
        t.fn();
      }
    }
  };

  check(
    "页面：收件人清单来自实例注册表（看板名，不写死）",
    (() => {
      const list = sandbox.__lp.knownTargets();
      return (
        list.indexOf("dsh-quant") >= 0 &&
        list.indexOf("codex-看板编辑") >= 0 &&
        list.indexOf("老板") >= 0 &&
        list.indexOf("codex-看板服务") >= 0 &&
        new Set(list).size === list.length
      );
    })(),
    sandbox.__lp.knownTargets().join(",")
  );
  check(
    "页面：@前缀识别（含 `-`、中文，最长 32）",
    sandbox.__lp.mentionPrefixOf("  @dsh-quant 干活") === "dsh-quant" &&
      sandbox.__lp.mentionPrefixOf("@老板 看下") === "老板" &&
      sandbox.__lp.mentionPrefixOf("没有前缀") === null,
    String(sandbox.__lp.mentionPrefixOf("  @dsh-quant 干活"))
  );

    // 兜底收件人：没写 @前缀时用它；写了前缀就以前缀为准
    sandbox.__lp.setTarget("dsh-quant");
    msgEl.value = "";
    check("页面：没写前缀 => 用选中的兜底收件人", sandbox.__lp.effectiveTarget() === "dsh-quant", sandbox.__lp.effectiveTarget());
    msgEl.value = "@老板 看下";
    check("页面：写了前缀 => 前缀覆盖兜底收件人", sandbox.__lp.effectiveTarget() === "老板", sandbox.__lp.effectiveTarget());
    sandbox.__lp.refreshRouteHint();
    check("页面：前缀生效时把兜底下拉置灰", targetSel.classList.contains("overridden") === true, "overridden=" + targetSel.classList.contains("overridden"));
    msgEl.value = "";
    sandbox.__lp.setTarget("codex");
    sandbox.__lp.refreshRouteHint();

    // ★ HUB-018 B（老板 2026-09-13 03:4x）：**老板面剔除组员↔组长的往来**——不进协作带、条数也不报。
    //   判据是"普通消息 + 两头都不是老板 + 至少一头是 member"。逐条钉死，免得以后放宽了口径没人发现。
    const noise = (from, to, kind) => sandbox.__lp.isMemberNoise({ from: from, to: to, kind: kind || "message" });
    check("老板面：组员→组长 的往来算噪声（老板面看不到、也不报条数）", noise("dsh-老员工", "codex-总监") === true);
    check("老板面：组长→组员 也算噪声（两个方向都要剔）", noise("codex-看板服务", "dsh-quant") === true);
    check("老板面：老板→组员 **不算**噪声（老板参与的一律留）", noise("老板", "dsh-老员工") === false);
    check("老板面：组员→老板 **不算**噪声（发给老板的照留）", noise("dsh-老员工", "老板") === false);
    check("老板面：组长↔组长 不算噪声（正常协作带）", noise("codex-看板服务", "codex-总监") === false);
    check("老板面：公告/进度等非普通消息不在这个判据里吞（各有各的规则）", noise("dsh-老员工", "codex-总监", "notice") === false);
    check("老板面：名册缺级别 => **fail-open**（宁多勿漏，别把主屏藏空）", noise("实习生甲", "实习生乙") === false);

    // 长按实例胶囊：450ms 才触发，触发后插入 @别名，有效收件人跟着前缀走
  const chip = fakeEl();
  let fired = 0;
  sandbox.__lp.addLongPress(chip, () => {
    fired++;
    sandbox.__lp.insertMention("dsh-老员工");
  });
  chip.dispatch("touchstart");
  const pending = timers.filter((t) => !t.dead);
  check("页面：长按进入等待（未满 450ms 不触发）", fired === 0 && pending.length === 1 && pending[0].ms === 450, "timers=" + pending.length + "/" + (pending[0] && pending[0].ms));
  runTimers();
  check("页面：长按 450ms 触发提及插入（插入的就是看板名）", fired === 1 && msgEl.value === "@dsh-老员工 ", JSON.stringify(msgEl.value));
  check("页面：插入提及后有效收件人跟着前缀", sandbox.__lp.effectiveTarget() === "dsh-老员工", sandbox.__lp.effectiveTarget());
  check("页面：提及有反馈（toast + 文案）", sandbox.__toasts.length === 1 && /已 @ 提及 dsh-老员工/.test(sandbox.__toasts[0]), JSON.stringify(sandbox.__toasts));
  check("页面：路由提示跟随 @前缀", /@dsh-老员工/.test(routeHint.textContent) && routeHint.style.display === "block", routeHint.textContent);

  // 触发后紧跟的那次 click 要被吃掉（否则胶囊会“又插提及又切筛选”）
  check("页面：长按后抑制误触 click", sandbox.__lp.lpSuppressClick() === true, "suppress=true");
  clock += 900;
  check("页面：900ms 后 click 恢复正常", sandbox.__lp.lpSuppressClick() === false, "suppress=false");

  // 手指滑走 / 提前松手都不该触发
  const chip2 = fakeEl();
  let fired2 = 0;
  sandbox.__lp.addLongPress(chip2, () => fired2++);
  chip2.dispatch("touchstart");
  chip2.dispatch("touchmove");
  runTimers();
  chip2.dispatch("touchstart");
  chip2.dispatch("touchend");
  runTimers();
  check("页面：滑动/提前松手取消长按", fired2 === 0, "fired=" + fired2);

  // 桌面右键 = 立即提及
  const chip3 = fakeEl();
  let fired3 = 0;
  sandbox.__lp.addLongPress(chip3, () => fired3++);
  chip3.dispatch("contextmenu");
  check("页面：右键即时插入提及", fired3 === 1, "fired=" + fired3);

  // 作者名长按：复用同一套（插完前面要留空格）
  msgEl.value = "结论是";
  sandbox.__lp.insertMention("老板");
  check("页面：作者名长按插入（自动补空格）", msgEl.value === "结论是 @老板 ", JSON.stringify(msgEl.value));

  // 审计"吵一次就够"：✕ 之后同样的旧账不再出现，新违规才再弹
  const vOld = { raw: "Codex", lastTs: "2026-09-10T21:10:00+08:00" };
  const vNew = { raw: "DSH", lastTs: "2026-09-10T22:00:00+08:00" };
  check("页面：审计默认都算“新”的", sandbox.__lp.freshViolations([vOld, vNew]).length === 2, "2");
  sandbox.localStorage.setItem("mchat_viol_ack", "2026-09-10T21:10:00+08:00");
  const after = sandbox.__lp.freshViolations([vOld, vNew]);
  check("页面：✕ 之后旧账不再提示、新违规照弹", after.length === 1 && after[0].raw === "DSH", JSON.stringify(after.map((v) => v.raw)));
}

async function main() {
  // 把环境事实写在最前面：跨环境排查"起不来/崩溃"时，先比这几行（总监 2026-09-13 门禁崩过）
  const shortName = /(^|[\\/])[^\\/]*~[0-9]/.test(TMP_BASE);
  process.stdout.write(
    "环境：node " + process.version + " · 临时根=" + TMP_BASE +
    (shortName ? " · ⚠️ 路径里仍含 8.3 短名（libuv fs.watch 会崩，建议 --tmp 指到别的盘）" : "") +
    "\n      本轮=" + ROOT + "\n"
  );
  setup();
  const child = spawn(process.execPath, [BOARD_MJS], {
    cwd: __dirname,
    env: {
      ...process.env,
      MCHAT_HOST: HOST,
      BOARD_PORT: String(PORT),
      MCHAT_DATA: dirs.data,
      MCHAT_INBOX_DIR: dirs.inbox,
      MCHAT_BRIDGE_DIR: dirs.bridge,
        MCHAT_BOARD_FILE: BOARD_FILE,
        MCHAT_DIALOG_FILE: DIALOG_FILE,
        MCHAT_AGENTS_FILE: AGENTS_FILE,
        MCHAT_CLAIM_TIMEOUT_MS: String(TIMEOUT_MS),
        // 信箱目录也要隔离：否则测试会往真实 outputs/dialog 里写 pending_*.ndjson
        MCHAT_MAILBOX_DIR: dirs.mailbox,
        // 任务卡目录也要隔离：否则 /api/tasks 建卡会往真仓库 docs/tasks/ 写
        MCHAT_TASKS_DIR: dirs.tasks,
        // 会话写锁目录也要隔离：否则测试要么读不到锁、要么污染真实 locks 目录
        MCHAT_THREAD_LOCKS: dirs.locks,
        // Codex CLI 换成桩程序：自测不碰真会话（生产默认走真 codex.exe，shell:false）
        MCHAT_CODEX_BIN: path.join(dirs.stub, "codex-stub.cmd"),
        MCHAT_CODEX_SHELL: "1",
        // 值守轮询调快：检索式代答的用例不必等 20 秒
        MCHAT_DUTY_POLL_MS: "3000",
        // 补投扫描周期调到 3 秒：让"退避到点必须被扫到"能在自测里几秒内验完（默认 60s）
        MCHAT_WAKE_RETRY_MS: "3000",
        // 公告 TTL 调到 9 秒（生产 24h）：才能把"入职晚于发布仍要回执"压缩进自测时限
        MCHAT_NOTICE_TTL_MS: "9000",
        // 用例里代答条数多，别被每小时限流干扰（生产仍是 10）
        MCHAT_DUTY_MAX_PER_HOUR: "50",
        // 队列硬冷却在用例里几乎关掉（生产 90s）；"同一条不重复投"仍生效，另有专门用例
        MCHAT_QUEUE_COOLDOWN_MS: "1",
        // 历史归档轮转：用例里把阈值调小，强制触发一次（生产 4MB）
        MCHAT_DIALOG_MAX_BYTES: "4000",
        MCHAT_DIALOG_KEEP_LINES: "10",
        // 审计只算「规约生效之后」的：把生效点设在夹具回帖（now-30min）之后、测试新写行之前
        MCHAT_NAME_AUDIT_SINCE: cst(new Date(NOW - 10 * MIN)),
      },
    stdio: ["ignore", "pipe", "pipe"],
  });
  childRef = child;
  let serverLog = "";
  const keep = (d) => {
    const s = d.toString("utf8");
    childLog += s;
    serverLog += s;
  };
  child.stdout.on("data", keep);
  child.stderr.on("data", keep);

  const tokenFile = path.join(dirs.data, "token.txt");
  const token = await waitFor(() => {
    try {
      const t = fs.readFileSync(tokenFile, "utf8").trim();
      return t.length >= 16 ? t : null;
    } catch {
      return null;
    }
  }, 10000);
  check("服务启动并生成 token", !!token);

  const base = "http://" + HOST + ":" + PORT;
  const hdr = { "x-mchat-token": token || "" };
  const ping = await waitFor(async () => {
    const r = await fetch(base + "/api/ping", { headers: hdr });
    return r.status === 200 ? await r.json() : null;
  }, 15000);
  check("GET /api/ping = 200", ping && ping.ok === true, JSON.stringify(ping));

  const r = await fetch(base + "/api/dialog?limit=200", { headers: hdr });
  const j = await r.json();
  check("GET /api/dialog = 200", r.status === 200, "status=" + r.status);

  // 回归：keepAliveTimeout 一旦被设大（如 60000），空闲几秒后的第一个请求会卡 ~25-29 秒才到服务端，
  // 手机页每 5 秒轮询、发消息都会跟着卡。这里用真实往返时间把它钉住。
  await new Promise((rr) => setTimeout(rr, 3000));
  const pingT0 = Date.now();
  await fetch(base + "/api/ping", { headers: hdr });
  const gapSec = (Date.now() - pingT0) / 1000;
  check("空闲 3 秒后第一个请求不卡（keepAliveTimeout 回归）", gapSec < 2, gapSec.toFixed(1) + "s");

  const records = j.records || [];
  const byInbox = (n) => records.find((x) => x.refs && x.refs.inbox === n);
  const byBridge = (id) => records.find((x) => x.refs && x.refs.bridge === id);
  const byBridgeTask = (id) => records.find((x) => x.refs && x.refs.bridgeTask === id);

  const overdue = byInbox("selftest_overdue.task.json");
  check("inbox：超时未回 => 待办", overdue && overdue.state === "待办" && overdue.overdue === true, overdue && overdue.state + "/overdue=" + overdue.overdue);
  check("inbox：记录归一字段（channel/kind/claimedBy）", overdue && overdue.channel === "inbox" && overdue.kind === "task" && overdue.claimedBy === "dsh-老员工", overdue && [overdue.channel, overdue.kind, overdue.claimedBy].join("|"));

  const cleared = byInbox("selftest_cleared_by_reply.task.json");
  check("接单锁：实例回帖后自动消 => done", cleared && cleared.state === "done", cleared && cleared.state);

  const fresh = byInbox("selftest_dispatched_fresh.task.json");
  check("inbox：未超时 => 已派单待回", fresh && fresh.state === "dispatched" && !fresh.overdue, fresh && fresh.state);

  const archived = records.find((x) => x.refs && x.refs.inbox === "selftest_archived.task.json");
  check("inbox：归档到 done/ => done", archived && archived.state === "done" && archived.refs.dir === "done", archived && archived.state + "/" + (archived.refs || {}).dir);

  const bmsg = byBridge("11111111-1111-1111-1111-111111111111");
  check("bridge：消息入 Hub（channel=bridge, kind=report，署名=看板名）", bmsg && bmsg.channel === "bridge" && bmsg.kind === "report" && bmsg.from === "dsh-老员工" && bmsg.to === "codex-看板服务", bmsg && [bmsg.channel, bmsg.kind, bmsg.from, bmsg.to].join("|"));
  check("bridge：未读且超时（发给 Codex）=> 待办", bmsg && bmsg.state === "待办", bmsg && bmsg.state);
  check("bridge：正文含进度/证据摘要", !!bmsg && /\[进度\]/.test(bmsg.body) && /\[证据\]/.test(bmsg.body), bmsg && bmsg.body.slice(0, 60));

  const bout = byBridge("22222222-2222-2222-2222-222222222222");
  check("bridge：Codex 自己发出的消息 => done", bout && bout.state === "done", bout && bout.state);

  const btask = byBridgeTask("33333333-3333-3333-3333-333333333333");
  check("bridge：任务（running）=> task/待办", btask && btask.kind === "task" && btask.channel === "bridge" && btask.state === "待办", btask && btask.kind + "/" + btask.state);

  const bdone = byBridgeTask("44444444-4444-4444-4444-444444444444");
  check("bridge：任务（completed）=> done", bdone && bdone.state === "done", bdone && bdone.state);

  const agents = j.agents || [];
  const dshAgent = agents.find((a) => a.alias === "dsh-老员工");
  const codexAgent = agents.find((a) => a.alias === "codex-看板服务");
  check("实例面板：dsh-老员工 有待办计数（状态栏用看板名）", dshAgent && dshAgent.open >= 1, dshAgent && "open=" + dshAgent.open);
  check("实例面板：codex-看板服务 有待办计数（桥未读）", codexAgent && codexAgent.open >= 1, codexAgent && "open=" + codexAgent.open);
  check(
    "状态栏芯片名 = 看板名（agents.json 全表）",
    agents.every((a) => /^(dsh-|codex-)/.test(a.alias) || a.alias === "老板") && agents.length >= 7,
    agents.map((a) => a.alias).join(",")
  );

  // 引用回复：POST /api/send 带 quoteId（发给「老板」不触发派单/不叫 Codex）
  const send = await fetch(base + "/api/send", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ target: "老板", message: "自测：引用回复正文", quoteId: bmsg ? bmsg.id : "", author: "老板" }),
  });
  const sendJson = await send.json();
  check("POST /api/send 引用回复返回 ok", send.status === 200 && sendJson.ok === true, JSON.stringify(sendJson));

  const r3 = await fetch(base + "/api/dialog?limit=200", { headers: hdr });
  const j3 = await r3.json();
  const quoted = (j3.records || []).find((x) => x.refs && x.refs.quote);
  check(
    "引用关系落进 Hub（refs.quote）",
    quoted && bmsg && quoted.refs.quote.id === bmsg.id && quoted.from === "老板" && /↩ 回复/.test(quoted.body),
    quoted && quoted.refs.quote.id
  );
  check("引用头写进看板行（人读得懂）", /↩ 回复/.test(fs.readFileSync(BOARD_FILE, "utf8")), "board line");

  // 参数校验
  const bad = await fetch(base + "/api/send", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ target: "codex", message: "", author: "老板" }),
  });
  check("POST /api/send 空消息被拒（400）", bad.status === 400, "status=" + bad.status);

  // —————————— CT-003：@前缀路由 / 目标校验 / 不误派 ——————————
  const inboxSet = () => new Set(fs.readdirSync(dirs.inbox).filter((n) => n.endsWith(".task.json")));
  const sendTo = async (payload) => {
    const rr = await timed("POST /api/send " + String(payload.message).slice(0, 12), () => fetch(base + "/api/send", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...hdr },
      // HUB-016：该口 require 显式署名；夹具默认以「老板」身份发（要测别的署名就自己传 author）
      body: JSON.stringify({ author: "老板", ...payload }),
    }));
    return { status: rr.status, body: await rr.json() };
  };
  const recordsNow = async () =>
    (await (await timed("GET /api/dialog", () => fetch(base + "/api/dialog?limit=50", { headers: hdr }))).json()).records || [];
  // 等 Hub 自己空闲：它忙着的时候 @ 一条会被判"Hub 正在处理别的回合"而延后（这是正确行为，
  // 但对"注入失败分类"这类用例是噪声干扰）——所以要投递前先等它空下来。
  const waitIdle = async (ms) => {
    const until = Date.now() + ms;
    while (Date.now() < until) {
      try {
        const p = await (await fetch(base + "/api/ping", { headers: hdr })).json();
        if (!p.busy) return true;
      } catch {}
      await new Promise((r) => setTimeout(r, 500));
    }
    return false;
  };
  // 看板文件按行取（多处用到：代答/标签/系统事实的判断都靠它）
  // 过滤空行：文件尾/幂等用例里会追加裸换行，不滤掉会让"行数增量"假加一（09:1x 踩过）
  const boardLines = () => fs.readFileSync(BOARD_FILE, "utf8").split("\n").filter((l) => l.trim());

  const beforeA = inboxSet();
  const prefA = await sendTo({ target: "codex", message: "@老板 [自测A] 前缀决定收件人，不该派单" });
  check("@前缀路由：接口返回 ok", prefA.status === 200 && prefA.body.ok === true, JSON.stringify(prefA.body));
  const recA = (await recordsNow()).filter((x) => String(x.body || "").includes("[自测A]")).pop();
  check("@前缀路由：收件人按前缀（覆盖单选里的 codex）", recA && recA.to === "老板", recA && "to=" + recA.to);

  await new Promise((r) => setTimeout(r, 2500));
  check("提及 @老板 不产生 inbox 任务（不误派）", inboxSet().size === beforeA.size, "before=" + beforeA.size + " after=" + inboxSet().size);

  const beforeB = inboxSet();
  const prefB = await sendTo({ target: "codex", message: "@dsh [自测B] 前缀派单，只此一条" });
  check("@前缀路由：派单消息返回 ok", prefB.status === 200 && prefB.body.ok === true, JSON.stringify(prefB.body));
  await new Promise((r) => setTimeout(r, 3500));
  const newTasks = [...inboxSet()].filter((n) => !beforeB.has(n));
  check("提及 @dsh 恰好派 1 个任务（不重复派单）", newTasks.length === 1 && /^board_dsh(_|-)/.test(newTasks[0]), newTasks.join(","));
  const taskRec = (await recordsNow()).find((x) => x.refs && /^board_dsh(_|-)/.test(String(x.refs.inbox || "")));
  check(
    "派单任务入 Hub 且带接单锁",
    taskRec && taskRec.channel === "inbox" && taskRec.kind === "task" && taskRec.to === "dsh-老员工" && taskRec.claimedBy === "dsh-老员工",
    taskRec && [taskRec.channel, taskRec.to, taskRec.claimedBy, taskRec.state].join("/")
  );

  // —— 命名规约验收（docs/BOARD_NAMES.md §6.4）：四处必须是同一串 ——
  const dispatchedName = taskRec && taskRec.to;
  const taskFile = [...inboxSet()].find((n) => /^board_dsh/.test(n));
  let taskJson = null;
  try {
    taskJson = JSON.parse(fs.readFileSync(path.join(dirs.inbox, taskFile), "utf8"));
  } catch {}
  const boardText = fs.readFileSync(BOARD_FILE, "utf8");
  const lastAck = boardText.split("\n").filter((l) => l.startsWith("- @老板") && /转投 inbox/.test(l)).pop() || "";
  check(
    "命名规约：inbox 指派名 = 看板名（instance/claimedBy）",
    taskJson && taskJson.instance === "dsh-老员工" && taskJson.claimedBy === "dsh-老员工" && /你是 dsh-老员工/.test(String(taskJson.do || "")),
    taskJson && [taskJson.instance, taskJson.claimedBy].join("/")
  );
  // 2026-09-10 老板反馈"看板服务比老员工还先发、刷屏" -> 转投成功后不再写回声行
  check("降噪：转投成功不再写看板回声（没有“转投 inbox”那一行）", !/转投 inbox/.test(boardText), "board 无回声行");
  check(
    "命名规约：旧句柄仍可用（@dsh 派给 dsh-老员工）",
    dispatchedName === "dsh-老员工" && taskJson && taskJson.to === "dsh-老员工",
    dispatchedName
  );

  const t1 = await sendTo({ target: "team-ops", message: "[自测] 目标校验：允许连字符" });
  check("目标校验：允许 `-`", t1.status === 200, "status=" + t1.status + " " + JSON.stringify(t1.body));
  const t2 = await sendTo({ target: "x".repeat(32), message: "[自测] 目标校验：32 字符" });
  check("目标校验：允许 32 字符", t2.status === 200, "status=" + t2.status);
  const t3 = await sendTo({ target: "x".repeat(33), message: "[自测] 目标校验：33 字符" });
  check("目标校验：33 字符被拒（400）", t3.status === 400, "status=" + t3.status);
  const t4 = await sendTo({ target: "dsh; rm -rf /", message: "[自测] 目标校验：非法字符" });
  check("目标校验：非法字符被拒（400）", t4.status === 400, "status=" + t4.status);
  const t5 = await sendTo({ target: "dsh-quant", message: "@dsh-quant [自测C] 实例别名路由" });
  check("目标校验：dsh-quant（带 `-` 的真实实例名）被接受", t5.status === 200, "status=" + t5.status);
  await new Promise((r) => setTimeout(r, 3000));
  const aliasTasks = [...inboxSet()].filter((n) => n.startsWith("board_dsh-quant_"));
  check("实例别名路由：派给 @dsh-quant 而不是默认实例", aliasTasks.length === 1, aliasTasks.join(","));

  const pageHtml = await (await fetch(base + "/", { headers: hdr })).text();
  const mainJs = servedPageJs(pageHtml);
  testServedPageSyntax(pageHtml);
  testPageMention(mainJs);
  testPageRender(j.records || [], mainJs);

  // —————————— 代答标签化 + 字体样式归一（老板 2026-09-11 08:1x）——————————
  const iRe = mainJs.indexOf("const MONO_RE");
  const iFn = mainJs.indexOf("function monoSplit");
  let monoSplit = null;
  try {
    const decl = iRe >= 0 && iFn > iRe ? mainJs.slice(iRe, iFn) : "";
    monoSplit = new Function(decl + grabFunction(mainJs, "monoSplit") + "\nreturn monoSplit;")();
  } catch (e) {
    monoSplit = null;
  }
  const parts = monoSplit ? monoSplit("自测：webread.py --head 2000 与 Z:\\tmp\\a.md 和 snake_case_id 都要等宽，中文别被切") : null;
  const codes = (parts || []).filter((x) => x.c).map((x) => x.s);
  check(
    "字体归一：纯文本里的英文标识符自动等宽（文件名 / --flag / 路径 / snake_case）",
    !!parts && codes.includes("webread.py") && codes.includes("--head") && codes.some((c) => c.indexOf(":\\") >= 0) && codes.includes("snake_case_id"),
    JSON.stringify(codes).slice(0, 150)
  );
  check(
    "字体归一：中文句子没有被切碎（宁可少套）",
    !!parts && parts.some((x) => !x.c && x.s.indexOf("中文别被切") >= 0),
    "ok"
  );

  // —————————— 成员自维护：合并式迁移 / 自动登记 / 署名审计 ——————————
  const cfgNow = () => JSON.parse(fs.readFileSync(AGENTS_FILE, "utf8"));
  check(
    "成员表：迁移只合并不覆盖（手工成员活下来）",
    !!cfgNow().agents["codex-手工成员"] && Number(cfgNow().schema) >= 2 && !!cfgNow().agents["codex-看板服务"],
    Object.keys(cfgNow().agents).length + " 条：" + Object.keys(cfgNow().agents).join(",")
  );
  check(
    "成员表：字段级补缺（老文件也能自动补上 threadId 这类新字段）",
    !!cfgNow().agents["codex-看板编辑"].threadId,
    String(cfgNow().agents["codex-看板编辑"].threadId || "(无)")
  );
  check("成员表：迁移前先备份 .bak", fs.existsSync(AGENTS_FILE + ".bak"), AGENTS_FILE + ".bak");

  // 一个没登记过的成员在看板上发言 → 应被自动登记；
  // 同时再写一条**没按规约署名**的新行（署名 Codex），用来验证审计只抓规约生效后的新账。
  fs.appendFileSync(BOARD_FILE, "- @老板 " + boardStamp(new Date()) + " codex-回测：自测成员，应自动登记\n", "utf8");
  fs.appendFileSync(BOARD_FILE, "- @老板 " + boardStamp(new Date()) + " Codex：自测署名未按规约（应被点名）\n", "utf8");
  await new Promise((rr) => setTimeout(rr, 2500));
  const j6 = await (await fetch(base + "/api/dialog?limit=50", { headers: hdr })).json();
  const auto = (j6.agents || []).find((a) => a.alias === "codex-回测");
  check("成员自动登记：新成员自己长进状态栏", !!(auto && auto.auto === true), auto ? JSON.stringify({ alias: auto.alias, auto: auto.auto, slug: (cfgNow().agents["codex-回测"] || {}).slug }) : "未登记");
  const autoSlug = (cfgNow().agents["codex-回测"] || {}).slug || "";
  check("成员自动登记：中文名也给合法 ASCII slug（不撞车、不残尾）", /^codex-[0-9a-f]{6}$/.test(autoSlug), autoSlug);
  check(
    "成员表：旧名折叠进实名（不出现两个芯片）",
    !cfgNow().agents["codex"] && !cfgNow().agents["dsh-main"] && (cfgNow().agents["codex-看板服务"].legacy || []).includes("codex"),
    JSON.stringify(cfgNow().agents["codex-看板服务"].legacy || [])
  );

  // 署名审计：只点名「规约生效后」写错的（老账豁免），且能给出归一目标
  const viol = j6.nameViolations || [];
  const vCodex = viol.find((v) => v.raw === "Codex");
  check("署名审计：规约生效后写错的被点名并给归一目标", !!(vCodex && vCodex.mapped === "codex-看板服务" && vCodex.count >= 1), JSON.stringify(viol.map((v) => v.raw + "→" + v.mapped)));
  check("署名审计：老账豁免（夹具里规约前的 DSH-main 不再刷屏）", !viol.some((v) => v.raw === "DSH-main"), JSON.stringify(viol.map((v) => v.raw)));
  check("署名审计：带生效点字段，前端可解释", !!j6.nameAuditSince, String(j6.nameAuditSince));

  // 状态自动维护：每个成员都带 idleMin/status，不靠手改 status 字段
  check(
    "状态自动维护：成员状态由“最近发言”现算",
    // retired 也是合法状态（HUB-013：退役档条目保持可见，但不算在岗）
    (j6.agents || []).every((a) => ["active", "idle", "stale", "none", "retired"].includes(a.status) && ("idleMin" in a)),
    (j6.agents || []).map((a) => a.alias + "=" + a.status).join(",")
  );

  // —— 回归：偏移错位 / 缺日期 ——
  // ① 往文件**最前面**插一行（会让所有后续字节偏移错位）：老实现会永久漏掉它
  const beforeInsert = fs.readFileSync(BOARD_FILE, "utf8");
  fs.writeFileSync(BOARD_FILE, "- @老板 " + boardStamp(new Date()) + " codex-回测2：插在最前面的一条\n" + beforeInsert, "utf8");
  // ② 少写日期的行（dsh 侧真出现过）：老解析器只认带日期的格式，会整条丢掉
  fs.appendFileSync(BOARD_FILE, "- @老板 " + boardTimeOnly(new Date()) + " dsh-老员工：缺日期也要能进来\n", "utf8");
  await new Promise((rr) => setTimeout(rr, 2500));
  const j7 = await (await fetch(base + "/api/dialog?limit=200", { headers: hdr })).json();
  const recIns = (j7.records || []).find((x) => String(x.body || "").includes("插在最前面的一条"));
  check("回归：插到文件前面的行也能入库（不再依赖字节偏移）", !!recIns && recIns.from === "codex-回测2", recIns ? recIns.from + "->" + recIns.to : "没入库");
  const recBare = (j7.records || []).find((x) => String(x.body || "").includes("缺日期也要能进来"));
  check(
    "回归：缺日期的看板行也能入库（自动补今天）",
    !!recBare && /^\d{4}-\d{2}-\d{2}T/.test(String(recBare.ts || "")) && recBare.from === "dsh-老员工",
    recBare ? recBare.ts : "没入库"
  );

  // 幂等：再拉一次不应产生重复记录
  const r2 = await fetch(base + "/api/dialog?limit=200", { headers: hdr });
  const j2 = await r2.json();
  const dup = (j2.records || []).filter((x) => x.refs && x.refs.inbox === "selftest_overdue.task.json").length;
  check("幂等：重复拉取不产生重复记录", dup === 1, "dup=" + dup);

  const lineCount = fs.readFileSync(DIALOG_FILE, "utf8").split("\n").filter(Boolean).length;
  check("dialog.ndjson 有落盘记录", lineCount > 0, "lines=" + lineCount);
  check(
    "性能：历史归档轮转（热文件超阈值 → 老行进 .archived，id 不丢）",
    fs.existsSync(DIALOG_FILE + ".archived") && fs.readFileSync(DIALOG_FILE + ".archived", "utf8").split("\n").filter(Boolean).length > 0,
    "archived=" + (fs.existsSync(DIALOG_FILE + ".archived") ? fs.readFileSync(DIALOG_FILE + ".archived", "utf8").split("\n").filter(Boolean).length : 0)
  );

  // —————————— 任务改号：CT-021/CT-022 → HUB-001/HUB-002（只读时归一）——————————
  const aliasRec = (j2.records || []).find((x) => x.refs && x.refs.inbox === "selftest_taskid_alias.task.json");
  check(
    "改号：界面上的旧号归一成新号（HUB-001 / HUB-002）",
    !!aliasRec && /HUB-001/.test(aliasRec.body) && /HUB-002/.test(aliasRec.body) && !/CT-02[12]/.test(aliasRec.body),
    aliasRec && aliasRec.body.slice(-48)
  );
  check(
    "改号：只在读取时归一，落盘原文不动（append-only）",
    (fs.readFileSync(DIALOG_FILE, "utf8") + "\n" +
      (fs.existsSync(DIALOG_FILE + ".archived") ? fs.readFileSync(DIALOG_FILE + ".archived", "utf8") : "")).includes("CT-021"),
    "dialog.ndjson 里仍保留旧号原文"
  );

  // —————————— HUB-002：投递判定（只读口，纯函数、无副作用）——————————
  const deliver = async (q) => {
    const rr = await fetch(base + "/api/deliver" + (q || ""), { headers: hdr });
    return { status: rr.status, body: await rr.json() };
  };
  const dActive = await deliver("?alias=" + encodeURIComponent("codex-测在岗"));
  check("HUB-002 判定：在岗且空闲 => inject（投递 + 唤醒）", dActive.status === 200 && dActive.body.action === "inject", JSON.stringify(dActive.body).slice(0, 150));
  check("HUB-002 判定：只认本条线，绝不改投别人", dActive.body.alias === "codex-测在岗", dActive.body.alias);
  const dRetired = await deliver("?alias=" + encodeURIComponent("codex-测退役"));
  check("HUB-002 判定：已退役 => retired（不投递、不兜底）", dRetired.body.action === "retired", dRetired.body.action);
  const dNobody = await deliver("?alias=" + encodeURIComponent("codex-测未上岗"));
  check("HUB-002 判定：没绑定会话 => unknown（只落信箱）", dNobody.body.action === "unknown", dNobody.body.action);
  const dNoAlias = await deliver("");
  check("HUB-002 判定：缺 alias 被拒（400）", dNoAlias.status === 400, "status=" + dNoAlias.status);
  const dNoToken = await fetch(base + "/api/deliver?alias=codex");
  check("HUB-002 判定：无 token 被拒（401）", dNoToken.status === 401, "status=" + dNoToken.status);
  check(
    "HUB-002 判定：退避阶梯可观测（2/5/15 分钟）",
    Array.isArray(dActive.body.backoffMs) && dActive.body.backoffMs.join(",") === "120000,300000,900000",
    String(dActive.body.backoffMs)
  );

  // —————————— HUB-002 口径修正：忙 ≠ 永远叫不醒 ——————————
  // 老板 2026-09-11 05:0x：「忙就只落信箱」= 永远叫不醒。正确口径 = 忙时不打扰 + **排定补投**。
  const mailboxFile = path.join(dirs.mailbox, "pending_codex-mtest.ndjson");
  const mailLines = () => {
    try {
      return fs.readFileSync(mailboxFile, "utf8").split("\n").filter((l) => l.trim()).length;
    } catch {
      return 0;
    }
  };
  const wakesNow = () => (JSON.parse(fs.readFileSync(path.join(dirs.data, "state.json"), "utf8")).wakes || {})["codex-测忙"] || {};

  const stBusy = await sendTo({ target: "codex-测忙", message: "[自测] 忙线补投：这条应先落信箱、再排补投" });
  check("忙线：@ 一条留言被接受", stBusy.status === 200, "status=" + stBusy.status);
  await new Promise((r) => setTimeout(r, 3500));
  check("忙线：留言落进它自己的信箱（不丢、不转别人）", mailLines() === 1, "lines=" + mailLines());
  const w1 = wakesNow();
  check(
    "忙线：**已排定补投**（不是静默压住 —— 口径修正的核心）",
    Number(w1.nextAt || 0) > Date.now() && Number(w1.attempts || 0) >= 1 && w1.done !== true,
    "还要等 " + Math.round((Number(w1.nextAt || 0) - Date.now()) / 1000) + "s · attempts=" + w1.attempts + " · done=" + w1.done
  );
  // 没被"唤醒"是硬要求；但**值守可以代答**（那是程序，不是本尊跑回合）——
  // 所以判据是"它自己发的话都带〔代答〕标签"，而不是"它一句话都没有"。
  const busyOwnLines = boardLines().filter((l) => l.indexOf("codex-测忙：") >= 0);
  check(
    "忙线：没被唤醒（它名下若出现发言，必须都是〔代答〕程序回的）",
    /DELIVER: codex-测忙 action=mailbox/.test(childLog) && busyOwnLines.every((l) => l.indexOf("〔代答〕") >= 0),
    "own=" + busyOwnLines.length
  );
  // 幂等：再触发一次扫描，不得重复投递
  fs.appendFileSync(BOARD_FILE, "\n", "utf8");
  await new Promise((r) => setTimeout(r, 2500));
  check("忙线：重复扫描不重复投递（幂等）", mailLines() === 1, "lines=" + mailLines());

  // 这条线变闲了：退避窗口内先别打扰（backoff），窗口一过就必须判成可投（inject）
  const cfgBusy = JSON.parse(fs.readFileSync(AGENTS_FILE, "utf8"));
  cfgBusy.agents["codex-测忙"].status = "active";
  cfgBusy.agents["codex-测忙"].threadId = "01a0bbbb-0000-7000-8000-000000000002";
  fs.writeFileSync(AGENTS_FILE, JSON.stringify(cfgBusy, null, 2), "utf8");
  const dStill = await deliver("?alias=" + encodeURIComponent("codex-测忙"));
  check(
    "忙线转闲：退避窗口内不立刻打扰（backoff）",
    dStill.body.action === "backoff" && Number(dStill.body.nextAt || 0) > Date.now(),
    dStill.body.action + " · 还要等 " + Math.round((Number(dStill.body.nextAt || 0) - Date.now()) / 1000) + "s"
  );
  const stateFile = path.join(dirs.data, "state.json");
  const stJson = JSON.parse(fs.readFileSync(stateFile, "utf8"));
  stJson.wakes["codex-测忙"].nextAt = 0; // 把退避拨到点
  fs.writeFileSync(stateFile, JSON.stringify(stJson, null, 2), "utf8");
  const dReady = await deliver("?alias=" + encodeURIComponent("codex-测忙"));
  check(
    "忙线转闲 + 退避到点 => inject（wakeRetryTick 会把这单补投进去）",
    dReady.body.action === "inject",
    dReady.body.action + " / " + (dReady.body.reason || "")
  );
  check("补投循环已接线（服务日志有 WAKE RETRY LOOP STARTED）", /WAKE RETRY LOOP STARTED/.test(childLog), "log");

  // ★ 回归（2026-09-12 真 bug · 现场抓到）：`done` 残留会把补投**静默跳过**——
  //   wakeRetryTick 第一句曾写 `if (b.done) continue`，而排定补投的几条写点只写 nextAt、
  //   不清 done，于是"退避到点后补投"在生产里从未真正发生过（日志里连一个字都没有）。
  //   这里按现场形状复现：{done:true, nextAt:<已过期>} + 信箱里有一条**新的**待补投留言
  //   → 修好后必须照样被扫到并留下动作行。
  fs.appendFileSync(
    mailboxFile,
    JSON.stringify({
      ts: cst(new Date()).slice(0, 16).replace("T", " "),
      from: "老板",
      to: "codex-测忙",
      body: "[自测] 补投回归：done 残留也要被扫到",
    }) + "\n",
    "utf8"
  );
  const stFix = JSON.parse(fs.readFileSync(stateFile, "utf8"));
  stFix.wakes["codex-测忙"] = { ...(stFix.wakes["codex-测忙"] || {}), done: true, nextAt: Date.now() - 1000 };
  fs.writeFileSync(stateFile, JSON.stringify(stFix, null, 2), "utf8");
  const logMark = childLog.length;
  let retrySeen = false;
  for (let i = 0; i < 6 && !retrySeen; i++) {
    await new Promise((r) => setTimeout(r, 1500)); // 自测里补投 poll=3s
    retrySeen = /WAKE RETRY (SKIP|OK|STILL BUSY|FAILED|STOP|DROP)/.test(childLog.slice(logMark));
  }
  const retryLine = (childLog.slice(logMark).split("\n").find((l) => /WAKE RETRY/.test(l)) || "").trim();
  check(
    "补投：done 残留 + 已到点 → 仍被扫到（不许静默跳过 · 2026-09-12 修）",
    retrySeen,
    retryLine.slice(0, 140) ||
      "没有 WAKE RETRY 动作行（= 被静默跳过）｜服务日志尾部：" + childLog.slice(-700).replace(/\s+/g, " ")
  );
  const afterFix = (JSON.parse(fs.readFileSync(stateFile, "utf8")).wakes || {})["codex-测忙"] || {};
  check(
    "补投：扫过之后账本必须收敛（不许停在过期的 nextAt 上）",
    Number(afterFix.nextAt || 0) === 0 || Number(afterFix.nextAt || 0) > Date.now(),
    "nextAt=" + (afterFix.nextAt || 0) + " done=" + afterFix.done
  );

  // —————————— HUB-002 must-fix（特批裁决 2026-09-11 05:0x）：锁文件在 ≠ 忙 ——————————
  fs.writeFileSync(path.join(dirs.locks, "01a0dddd-0000-7000-8000-000000000003.lock"), "", "utf8");
  fs.writeFileSync(path.join(dirs.locks, "01a0eeee-0000-7000-8000-000000000004.lock"), "", "utf8");
  // 拉模式可见化夹具：信箱里先压一条**旧的**（早于它发言 → 不该算未读）
  const mailTs = (d) => cst(d).slice(0, 16).replace("T", " ");
  const awakeMailFile = path.join(dirs.mailbox, "pending_codex-awake2.ndjson");
  fs.writeFileSync(
    awakeMailFile,
    JSON.stringify({ ts: mailTs(new Date(NOW - 90 * MIN)), from: "老板", to: "codex-测窗口", body: "自测：这条很早，等它发言后就不该算未读" }) + "\n",
    "utf8"
  );
  const dLocked = await deliver("?alias=" + encodeURIComponent("codex-测窗口"));
  check(
    "特批 must-fix：锁文件在 + 久无产出 **不再**直接判忙（给投递机会）",
    dLocked.body.action === "inject" && dLocked.body.lockPresent === true && dLocked.body.lastOutputSec === null,
    dLocked.body.action + " · lockPresent=" + dLocked.body.lockPresent + " · lastOutputSec=" + dLocked.body.lastOutputSec
  );

  // ② 闲时叫得动（**真送达**）：桩被唤醒并回话 → 回话落到看板
  check("闲时叫得动：投递前 Hub 已空闲", await waitIdle(15000), "idle");
  const stAwake = await sendTo({ target: "codex-测窗口", message: "[自测] 闲时叫得动：应当被唤醒并回话" });
  check("闲时叫得动：@ 一条被接受", stAwake.status === 200, "status=" + stAwake.status);
  await new Promise((r) => setTimeout(r, 4500));
  const boardNow = fs.readFileSync(BOARD_FILE, "utf8");
  check(
    "闲时叫得动（REQ-HUB-004b）：首选 `codex queue` 命中 → 判为**已投递+已唤醒**",
    /DELIVERED\+WOKEN: codex-测窗口 via=queue/.test(childLog),
    "queue wake"
  );
  // 拉模式可见化：它一发言，信箱里那条旧留言就不该再算"未读"；再压一条新的 → 计 1
  const agentMail = async (name) =>
    ((await (await fetch(base + "/api/dialog?limit=50", { headers: hdr })).json()).agents || [])
      .find((a) => a.alias === name) || {};
  const mailAfterPost = (await agentMail("codex-测窗口")).pendingMail;
  check("拉模式可见化：压在信箱里的留言会计成「未读」", mailAfterPost >= 1, "pendingMail=" + mailAfterPost);
  fs.appendFileSync(
    awakeMailFile,
    // +5 分钟：同一分钟内 ts 相等会被判成"不更新"，这里要的是"比它发言新"
    JSON.stringify({ ts: mailTs(new Date(Date.now() + 5 * MIN)), from: "老板", to: "codex-测窗口", body: "自测：这条比它发言新，应该算未读" }) + "\n",
    "utf8"
  );
  const mailNew = (await agentMail("codex-测窗口")).pendingMail;
  check(
    "拉模式可见化：新留言让「信箱 N」加一（状态栏显示）",
    mailNew === mailAfterPost + 1,
    "before=" + mailAfterPost + " after=" + mailNew
  );
  // 时间戳兼容：board @ 转投写的老格式是**只有 HH:MM**（没有日期）。解析不出来就会被当成
  // "太老"→ 值班分线静默跳过（2026-09-11 05:3x 抓到的静默丢）。这条钉住它。
  fs.appendFileSync(
    awakeMailFile,
    JSON.stringify({ ts: "23:59", from: "老板", to: "codex-测窗口", body: "自测：只有 HH:MM 的时间戳也要能算" }) + "\n",
    "utf8"
  );
  const mailBare = (await agentMail("codex-测窗口")).pendingMail;
  check(
    "信箱时间戳：只有 HH:MM 的老格式也算得出来（不再被判成「太老」）",
    mailBare === mailNew + 1,
    "pendingMail=" + mailBare
  );

  // ★ 未读口径（codex-总监 2026-09-12 22:24 正式请求 · 与宿主 crew_host.py 对齐）
  //   **未读 = 该线信箱里 ts 比它"本人上一次发言"更新的行**。以前按信箱原始行数算，
  //   append-only 流水没有已读概念 → 几天前早回过几百遍的旧信也被算未读，芯片/门铃一路虚高。
  const unreadFile = path.join(dirs.mailbox, "pending_codex-unread.ndjson");
  const mailOf = agentMail;
  fs.writeFileSync(
    unreadFile,
    JSON.stringify({ ts: mailTs(new Date(Date.now() - 60 * MIN)), from: "老板", to: "codex-测未读", body: "自测：这条在它发言之前，一发言就不该再算未读" }) + "\n",
    "utf8"
  );
  const nBeforeSpeak = (await mailOf("codex-测未读")).pendingMail;
  check("未读口径①：它还没发言时，那条旧留言算未读", nBeforeSpeak === 1, "pendingMail=" + nBeforeSpeak);
  // 本人在板上真的发言一行 → 那条旧留言随即不再计入
  const rSpeak = await fetch(base + "/api/post", {
    method: "POST",
    headers: { ...hdr, "Content-Type": "application/json" },
    body: JSON.stringify({ author: "codex-测未读", target: "老板", body: "[自测] 本人发言：我说话了" }),
  });
  check("未读口径②：本人能发言（板上一行）", rSpeak.ok, "status=" + rSpeak.status);
  await new Promise((r) => setTimeout(r, 1200));
  const nAfterSpeak = (await mailOf("codex-测未读")).pendingMail;
  check("未读口径②：本人发言后，之前的留言自动不计入（清空后 N=0）", nAfterSpeak === 0, "pendingMail=" + nAfterSpeak);
  // 真新留言（ts 比本人发言新）→ 必须 +1
  fs.appendFileSync(
    unreadFile,
    JSON.stringify({ ts: mailTs(new Date(Date.now() + 2 * MIN)), from: "老板", to: "codex-测未读", body: "自测：这条比本人发言新 → 算未读" }) + "\n",
    "utf8"
  );
  const nNew = (await mailOf("codex-测未读")).pendingMail;
  check("未读口径③：真新留言让 N 回到 1（不是 0，也不是原始行数 2）", nNew === 1, "pendingMail=" + nNew);
  // 〔代答〕**不算**本人发言：给它自己写一条**比新留言更晚**的〔代答〕（直接进记录真源）。
  // 若被误算成"本人发言"，上面那条新留言就会被吞掉（N 会变 0）——这条用例就是钉这个。
  fs.appendFileSync(
    DIALOG_FILE,
    JSON.stringify({
      id: "selftest-duty-" + Date.now(),
      ts: cst(new Date(Date.now() + 3 * MIN)).slice(0, 16).replace("T", " "),
      from: "codex-测未读",
      to: "老板",
      channel: "board",
      kind: "message",
      body: "〔代答〕您好，我现在不在，请稍后再试。",
      state: "done",
    }) + "\n",
    "utf8"
  );
  await new Promise((r) => setTimeout(r, 1200));
  const nDuty = (await mailOf("codex-测未读")).pendingMail;
  check("未读口径④：代答不算本人发言（新留言仍算未读）", nDuty === 1, "pendingMail=" + nDuty);
  // 退役档案条目：不是活人 → 不叫、也不该显示未读
  fs.writeFileSync(
    path.join(dirs.mailbox, "pending_codex-retired.ndjson"),
    JSON.stringify({ ts: mailTs(new Date()), from: "老板", to: "codex-测退役", body: "自测：退役档案条目的信箱不该被算未读" }) + "\n",
    "utf8"
  );
  const nRetired = (await mailOf("codex-测退役")).pendingMail;
  check("未读口径⑤：退役档案条目不计未读（不叫也不虚高）", nRetired === 0, "pendingMail=" + nRetired);

  // ③ 抢锁失败 + 久无产出 => 「已投递未唤醒」，**停止**无限退避
  check("窗口占用：投递前 Hub 已空闲", await waitIdle(15000), "idle");
  const stOcc = await sendTo({ target: "codex-测占用", message: "[自测] 窗口占用但空闲：不该无限退避" });
  check("窗口占用：@ 一条被接受", stOcc.status === 200, "status=" + stOcc.status);
  await new Promise((r) => setTimeout(r, 4500));
  const wakesOcc = (JSON.parse(fs.readFileSync(path.join(dirs.data, "state.json"), "utf8")).wakes || {})["codex-测占用"] || {};
  check(
    "窗口占用但空闲 => parked（停止重试，不再无限退避）",
    wakesOcc.parked === true && wakesOcc.done === true && Number(wakesOcc.nextAt || 0) === 0,
    JSON.stringify(wakesOcc).slice(0, 160)
  );
  const boardOcc = fs.readFileSync(BOARD_FILE, "utf8");
  check("窗口占用但空闲 => 看板显式标注「已投递未唤醒」", /已投递未唤醒/.test(boardOcc), "annotated");
  // 代答/系统标注一律"标签化"，不再写"（本尊这会儿不在，由…代答）"这种长解释（老板 2026-09-11 08:1x）
  check("标签化：已投递未唤醒只用标签", /〔已投递未唤醒〕/.test(boardOcc), "tag");
  check("标签化：不再写「本尊这会儿不在…的值守分线代答」长句", !/本尊这会儿不在/.test(boardOcc), "no-boilerplate");
  const occMail = (() => {
    try {
      return fs.readFileSync(path.join(dirs.mailbox, "pending_codex-occ.ndjson"), "utf8").split("\n").filter((l) => l.trim()).length;
    } catch {
      return 0;
    }
  })();
  check("窗口占用但空闲 => 留言仍在它信箱（没丢、没转别人）", occMail === 1, "lines=" + occMail);
  check("注入确实被尝试过（日志有 INJECT FAILED / WINDOW IDLE）", /INJECT FAILED|WINDOW IDLE/.test(childLog), "log");

  // —————————— HUB-003 向上敲门铃（降级版：上板 @老板 + 置顶）——————————
  const bossPost = async (p) => {
    const rr = await fetch(base + "/api/boss-event", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...hdr },
      body: JSON.stringify(p),
    });
    return { status: rr.status, body: await rr.json() };
  };
  const e1 = await bossPost({ from: "codex-测在岗", kind: "accept", task: "KIT-999", needAction: "请你验收 M0 交付（报告在 docs/reports/x.md）" });
  check("门铃①：待验收事件被接受", e1.status === 200 && e1.body.ok === true && e1.body.board === true, JSON.stringify(e1.body));
  const e2 = await bossPost({ from: "codex-测在岗", kind: "decide", task: "KIT-998", needAction: "需要你授权提交这次契约变更" });
  check("门铃①：需拍板事件被接受", e2.status === 200 && e2.body.ok === true, JSON.stringify(e2.body));
  const e3 = await bossPost({ from: "codex-测在岗", kind: "incident", task: "KIT-997", needAction: "引擎掉线已处置，需要你决定是否回滚参数" });
  check("门铃①：故障事件被接受", e3.status === 200 && e3.body.ok === true, JSON.stringify(e3.body));
  const bt = fs.readFileSync(BOARD_FILE, "utf8");
  check(
    "门铃①：**一律上板并 @老板**（三条都在看板上）",
    bt.includes("【待老板·") && bt.includes("KIT-999") && bt.includes("KIT-998") && bt.includes("KIT-997"),
    "board lines"
  );
  const e4 = await bossPost({ from: "codex-测在岗", kind: "chat", task: "KIT-996", needAction: "随便说一句" });
  check("门铃②：非三类事件被拒（400）", e4.status === 400, JSON.stringify(e4.body));
  const e5 = await bossPost({ from: "codex-测在岗", kind: "accept", task: "KIT-995", needAction: "好" });
  check("门铃③：没写清「要你做什么」被拒（400）", e5.status === 400, JSON.stringify(e5.body));
  const e6 = await bossPost({ from: "codex-不存在", kind: "accept", needAction: "请你验收" });
  check("门铃④：未注册署名被拒（400）", e6.status === 400, JSON.stringify(e6.body));
  const e7 = await bossPost({ from: "codex-测在岗", kind: "accept", task: "KIT-999", needAction: "请你验收 M0 交付（重复触发）" });
  check("门铃⑤：同任务 10 分钟内节流（不重复推）", e7.status === 200 && e7.body.throttled === true, JSON.stringify(e7.body));
  const bossJson = async () => (await (await fetch(base + "/api/dialog?limit=50", { headers: hdr })).json()).boss || {};
  const b1 = await bossJson();
  check("门铃⑥：置顶数据 = 「待老板：N 条」", b1.count === 3, JSON.stringify({ count: b1.count, today: b1.today }));
  check("门铃⑦：每条都带「要你做什么」", (b1.items || []).every((x) => String(x.needAction || "").length >= 4), "ok");
  await fetch(base + "/api/boss-mute", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ on: true }),
  });
  const b2 = await bossJson();
  check("门铃⑧：静音只关「打扰」，事件仍在（不丢）且界面看得出已静音", b2.muted === true && b2.count === 3, JSON.stringify({ muted: b2.muted, count: b2.count }));
  await fetch(base + "/api/send", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ target: "codex-测在岗", message: "[自测] 老板看到置顶了", author: "老板" }),
  });
  await new Promise((r) => setTimeout(r, 1500));
  const b3 = await bossJson();
  check("门铃⑨：老板一发言即视为「看到」，置顶清空", b3.count === 0, "count=" + b3.count);

  // —————————— 代答从根上改：**只检索、不生成**（老板 2026-09-11 08:2x："千万不能脑补"）——————————
  const mailTo = async (to, body, from) => {
    const rr = await fetch(base + "/api/mail", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...hdr },
      body: JSON.stringify({ to: to, from: from || "老板", body: body }),
    });
    return rr.status;
  };
  // 代答只给**没有本尊会话的真·空席位**（2026-09-12 00:2x 老板拍板），这里用 codex-测无会话
  fs.appendFileSync(BOARD_FILE, "- @老板 " + boardStamp(new Date()) + " codex-测无会话：自测锚点：守望编号 ZQ-7788 的处置方式是 reboot guard。\n", "utf8");
  await new Promise((r) => setTimeout(r, 2500));
  const beforeDuty = boardLines().length;
  // ① 能引述 → 必须出【引述·本线 …】+ 出处
  //    （2026-09-11 23:4x 抬头从「本尊」改成「本线」：本线自己的历史发言挂"本尊"名牌，
  //      老板会读成"这话是我说的"——等于冒名。改由 codex-总监 落，本线复核后对齐断言。）
  await mailTo("codex-测无会话", "守望编号 ZQ-7788 的处置方式是什么？");
  const gotQuote = await waitFor(() => /〔代答〕【引述·本线 /.test(boardLines().join("\n")), 20000);
  check(
    "代答①引述：命中原话时只给【引述·本线 …】+ 出处",
    !!gotQuote && /ZQ-7788/.test(boardLines().join("\n")) && /出处：Hub 记录 /.test(boardLines().join("\n")),
    "quote"
  );
  // ② 找不到 → 只能回【未决】
  const hadPendBefore = /〔代答〕您好，我现在不在，请稍后再试/.test(boardLines().join("\n"));
  await mailTo("codex-测无会话", "那个不存在的代号 XQ-0000 该怎么处置？");
  const gotPend = await waitFor(() => /〔代答〕您好，我现在不在，请稍后再试/.test(boardLines().join("\n")), 25000);
  check(
    "代答②未决：找不到出处时只回一句「您好，我现在不在，请稍后再试。」",
    !hadPendBefore && !!gotPend,
    "before=" + hadPendBefore + " got=" + !!gotPend
  );
  // ③ 老板说话**必须有回应**（2026-09-11 08:43 教训：他发"辛苦了"，谁都没回）
  // 注意：别的用例可能已经产生过同样的"收到"文案，所以这里按**行数增量**判，不能按全局文案判
  const beforeAck = boardLines().length;
  await mailTo("codex-测无会话", "辛苦了");
  const gotAck = await waitFor(
    () => boardLines().length > beforeAck && /〔代答〕收到。/.test(boardLines().slice(beforeAck).join("\n")),
    60000 // 值守一轮只答一条（全局），用例里多线排队，给足时间
  );
  check(
    "代答③老板的纯礼貌话也要回一句「收到」（不能让他觉得系统坏了）",
    !!gotAck,
    "new=" + (boardLines().length - beforeAck) + " tail=" + boardLines().slice(beforeAck).join("|").slice(-70)
  );
  // ③之二 别的线的纯礼貌话 → 仍然不回（少刷屏）
  const beforePolite = boardLines().length;
  await mailTo("codex-测无会话", "辛苦了", "codex-总监");
  await new Promise((r) => setTimeout(r, 9000));
  check("代答③之二：其它线的纯礼貌话不回", boardLines().length === beforePolite, "lines=" + (boardLines().length - beforePolite));
  // ④ 服务不冒充：给"没有绑会话、也没值守"的线 @ 一条 → 只能有**服务自己署名**的系统事实
  await waitIdle(12000);
  const beforeSvc = boardLines().length;
  await sendTo({ target: "codex-测无值守", message: "[自测] 系统事实：这条线没人值守" });
  await new Promise((r) => setTimeout(r, 4000));
  const svcNew = boardLines().slice(beforeSvc).join("\n");
  check(
    "服务不冒充：无值守的线只发服务自己署名的系统事实",
    /（系统：@codex-测无值守/.test(svcNew) && /codex-看板服务/.test(svcNew) && !/codex-测无值守：/.test(svcNew),
    svcNew.slice(-90)
  );
  check("代答路径不再调模型（日志没有 DUTY ANSWER FAILED / 值守分线启动失败）", !/DUTY ANSWER FAILED|值守分线启动失败/.test(childLog), "log");

  // ⑤ 值守配置化（2026-09-12 00:2x 新口径）：**有本尊的线不代答；真·空席位才代答**；老板/服务永不设
  const agentsDuty = ((await (await fetch(base + "/api/dialog?limit=50", { headers: hdr })).json()).agents || []);
  const dutyOf = (n) => (agentsDuty.find((a) => a.alias === n) || {}).duty;
  check("代答口径：真·空席位（无会话）才代答", dutyOf("codex-测无会话") === true && dutyOf("dsh-老员工") === true, "ok");
  check("代答口径：已绑本尊的线**不代答**（本尊优先）", dutyOf("codex-测在岗") === false && dutyOf("codex-测占用2") === false, "ok");
  check("值守配置化：系统角色 codex-看板服务 永不设值守", dutyOf("codex-看板服务") === false, String(dutyOf("codex-看板服务")));
  check("值守配置化：显式 duty:false 可关掉", dutyOf("codex-测无值守") === false, String(dutyOf("codex-测无值守")));
  // ⑥ 有本尊的线**不许**代答：往它信箱问一句 → 板上不该出现它署名的〔代答〕
  const beforeNoDuty = boardLines().length;
  await mailTo("codex-测在岗", "编号 QA-4242 的处置方式是什么？");
  await new Promise((r) => setTimeout(r, 9000));
  check(
    "有本尊的线不代答：板上不出现它署名的〔代答〕",
    !boardLines().slice(beforeNoDuty).some((l) => l.indexOf("codex-测在岗：") >= 0 && l.indexOf("〔代答〕") >= 0),
    "no-duty-for-bound"
  );
  // ⑦ 窗口占用 + **有本尊**（不代答）→ 落信箱 + 标「已投递未唤醒」（不再替它说话）
  await waitIdle(12000);
  const beforeOcc2 = boardLines().length;
  await sendTo({ target: "codex-测占用2", message: "[自测] 窗口占用但有值守：请回答一个查不到的问题 XQ-9" });
  const gotOcc2 = await waitFor(() => /已投递未唤醒/.test(boardLines().slice(beforeOcc2).join("\n")), 40000);
  check(
    "窗口占用 + 有本尊 => 落信箱 + 标「已投递未唤醒」（**不代答**）",
    !!gotOcc2 && !boardLines().slice(beforeOcc2).some((l) => l.indexOf("codex-测占用2：") >= 0 && l.indexOf("〔代答〕") >= 0),
    boardLines().slice(beforeOcc2).join("\n").slice(-80)
  );
  // 停用会话（老板 A 方案）：投递口必须绕开它，不许把"睡着的会话"叫起来
  check(
    "闲置会话停用：投递口绕开它（日志 RETIRED THREAD），不 queue",
    /RETIRED THREAD: 不投递 codex-测占用2/.test(childLog) &&
      !/DELIVERED\+WOKEN: codex-测占用2 via=queue/.test(childLog),
    "retired skipped"
  );

  // ⑧ REQ-HUB-004b：queue 不通时退到 `codex exec resume`（窗口关着时它反而能成）
  await waitIdle(12000);
  await sendTo({ target: "codex-测备用", message: "[自测] queue 不通时走备用路径" });
  const gotBackup = await waitFor(() => /selftest stub resume reply/.test(boardLines().join("\n")), 30000);
  check(
    "投递即唤醒 · 备用：queue 不通 → resume 仍送达（回话落看板）",
    !!gotBackup && /via=resume/.test(childLog),
    "backup path"
  );
  // ⑨ 路径动态解析 + 署名归发起线
  const ping2 = await (await fetch(base + "/api/ping", { headers: hdr })).json();
  check(
    "codex 路径动态解析（不再写死版本哈希）",
    typeof ping2.codexBin === "string" && /codex/i.test(ping2.codexBin),
    ping2.codexBin
  );
  await fetch(base + "/api/send", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ target: "codex-测在岗", message: "[自测] 署名归发起线", author: "codex-测在岗" }),
  });
  await new Promise((r) => setTimeout(r, 1500));
  check(
    "/api/send 署名：给了 author 就署它（不再一律写死「老板」）",
    boardLines().some((l) => l.indexOf("codex-测在岗：") >= 0 && l.indexOf("[自测] 署名归发起线") >= 0),
    "author honored"
  );
  const badAuthor = await fetch(base + "/api/send", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ target: "老板", message: "[自测] 没注册的署名", author: "codex-冒名" }),
  });
  check("/api/send 署名：没注册的 author 被拒（400）", badAuthor.status === 400, "status=" + badAuthor.status);

  // ⑨之三 HUB-016（总监 2026-09-13 02:17 批准）：`/api/send` **必须显式署名**——token 只证明
  //   有权用这个入口、**不决定署名**（HUB-004 卡面）。四条判别性用例，缺一条这条改动就没闭环。
  const h16 = async (payload) => {
    const r = await fetch(base + "/api/send", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...hdr },
      body: JSON.stringify(payload),
    });
    return { status: r.status, body: await r.json().catch(() => ({})) };
  };
  const r1601 = await h16({ target: "老板", message: "[自测] HUB-016 这条不带署名" });
  check("HUB-016①：不带 author → 400（不许默认落成「老板」）", r1601.status === 400, "status=" + r1601.status);
  const r1602 = await h16({ target: "老板", message: "[自测] HUB-016 冒名", author: "codex-不存在" });
  check("HUB-016②：未注册的 author → 400", r1602.status === 400, "status=" + r1602.status);
  await h16({ target: "老板", message: "[自测] HUB-016 署看板名", author: "codex-测在岗" });
  await h16({ target: "老板", message: "[自测] HUB-016 署老板", author: "老板" });
  await new Promise((r) => setTimeout(r, 1500));
  const d16 = await (await fetch(base + "/api/dialog?limit=50", { headers: hdr })).json();
  const recLine = (kw) => (d16.records || []).filter((r) => String(r.body || "").indexOf(kw) >= 0).pop();
  const rec1603 = recLine("HUB-016 署看板名");
  check(
    "HUB-016③：带注册名 → 就落该名（不再一律写死「老板」）",
    !!rec1603 && rec1603.from === "codex-测在岗",
    rec1603 ? rec1603.from : "no record"
  );
  const rec1604 = recLine("HUB-016 署老板");
  check(
    "HUB-016④：author=\"老板\" → 落「老板」（页面路径不变）",
    !!rec1604 && rec1604.from === "老板",
    rec1604 ? rec1604.from : "no record"
  );

  // ⑩ 承诺词自动标注（最小化：只挂一枚小圆角标签，不写长句）
  fs.appendFileSync(
    BOARD_FILE,
    "- @老板 " + boardStamp(new Date()) + " codex-测无会话：自测锚点3：编号 PT-5150 的事我同意按方案 A 执行。\n",
    "utf8"
  );
  await new Promise((r) => setTimeout(r, 2500));
  await mailTo("codex-测无会话", "编号 PT-5150 那件事你同意了吗？");
  const gotPromise = await waitFor(() => /〔代答〕〔承诺需本尊确认〕/.test(boardLines().join("\n")), 40000);
  check("承诺词自动标注：引述到承诺类内容时挂小标签「承诺需本尊确认」", !!gotPromise, "promise tag");

  // ⑪ HUB-001 绑定/换绑
  const bindRes = await fetch(base + "/api/bind", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ alias: "codex-测在岗", threadId: "01a02222-0000-7000-8000-000000000007", why: "自测换绑" }),
  });
  const bindBody = await bindRes.json();
  const cfgAfterBind = JSON.parse(fs.readFileSync(AGENTS_FILE, "utf8"));
  check(
    "绑定/换绑：走 API 就能换，旧号自动归档进 failedThreadIds",
    bindRes.status === 200 && bindBody.replaced === "01a0aaaa-0000-7000-8000-000000000001" &&
      (cfgAfterBind.agents["codex-测在岗"].failedThreadIds || []).includes("01a0aaaa-0000-7000-8000-000000000001"),
    JSON.stringify(bindBody).slice(0, 120)
  );
  const badBind = await fetch(base + "/api/bind", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ alias: "codex-测在岗", threadId: "不是UUID" }),
  });
  check("绑定：threadId 格式不对被拒（400）", badBind.status === 400, "status=" + badBind.status);

  // ⑪之二 HUB-001 入职：给**新线**发牌（这是"新窗口走员工流程"缺的那一步）
  const onboard = (body) =>
    fetch(base + "/api/onboard", { method: "POST", headers: { "Content-Type": "application/json", ...hdr }, body: JSON.stringify(body) });
  const obOk = await onboard({
    by: "codex-看板编辑",
    approval: "老板 2026-09-13 自测口述",
    name: "codex-测新线",
    slug: "codex-newline",
    threadId: "01a03333-0000-7000-8000-000000000008",
    title: "自测新线",
  });
  const obBody = await obOk.json();
  const cfgAfterOb = JSON.parse(fs.readFileSync(AGENTS_FILE, "utf8"));
  check(
    "入职：新线能登记进名册（工号/会话/批准人都在）",
    obOk.status === 200 && obBody.ok === true && cfgAfterOb.agents["codex-测新线"] &&
      cfgAfterOb.agents["codex-测新线"].slug === "codex-newline" &&
      cfgAfterOb.agents["codex-测新线"].threadId === "01a03333-0000-7000-8000-000000000008" &&
      /批准：老板 2026-09-13/.test(String(cfgAfterOb.agents["codex-测新线"].note || "")),
    JSON.stringify(obBody).slice(0, 120)
  );
  // 入职完就该能派活：投它信箱必须成功（不然"流程"是空的）
  const obMail = await fetch(base + "/api/mail", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ to: "codex-测新线", from: "codex-看板编辑", body: "自测：入职后应当能收到信" }),
  });
  check("入职：入册后立刻能被投信（信箱通道打通）", obMail.status === 200, "status=" + obMail.status);
  const obDup = await onboard({ by: "codex-看板编辑", approval: "老板 口述", name: "codex-测新线", slug: "codex-newline2" });
  check("入职：重名被拒（409）", obDup.status === 409, "status=" + obDup.status);
  const obSlugDup = await onboard({ by: "codex-看板编辑", approval: "老板 口述", name: "codex-测新线2", slug: "codex-mtest" });
  check("入职：工号已被占用被拒（409，工号不撞号）", obSlugDup.status === 409, "status=" + obSlugDup.status);
  const obSlugRetired = await onboard({ by: "codex-看板编辑", approval: "老板 口述", name: "codex-测新线3", slug: "codex-retired" });
  check("入职：退役条目的工号也不许复用（409）", obSlugRetired.status === 409, "status=" + obSlugRetired.status);
  const obNoApproval = await onboard({ by: "codex-看板编辑", name: "codex-测新线4", slug: "codex-newline4" });
  check("入职：没写批准人被拒（400，发牌必须有人拍板）", obNoApproval.status === 400, "status=" + obNoApproval.status);
  const obBadBy = await onboard({ by: "codex-不存在", approval: "老板 口述", name: "codex-测新线5", slug: "codex-newline5" });
  check("入职：by 不是注册看板名被拒（400，署名实名）", obBadBy.status === 400, "status=" + obBadBy.status);
  const obTidTaken = await onboard({ by: "codex-看板编辑", approval: "老板 口述", name: "codex-测新线6", slug: "codex-newline6", threadId: "01a02222-0000-7000-8000-000000000007" });
  check("入职：会话已被别的线占用被拒（409，一个会话只属于一条线）", obTidTaken.status === 409, "status=" + obTidTaken.status);
  // ⑪之三 slug 跨系统契约对齐（唯一规范：套件仓 docs/slug.md）
  const metaSlug = await (await fetch(base + "/api/meta")).json();
  const anchors = (metaSlug.slugContract || {}).anchors || {};
  check(
    "slug 契约：锚点与套件仓 docs/slug.md 一致（codex-套件=9bb7a0 / dsh-老员工=e18b10 / codex-甲=d0e43b / codex-乙=a3162a）",
    anchors["codex-套件"] === "codex-9bb7a0" && anchors["dsh-老员工"] === "dsh-e18b10" &&
      anchors["codex-甲"] === "codex-d0e43b" && anchors["codex-乙"] === "codex-a3162a",
    JSON.stringify(anchors)
  );
  check("slug 契约：唯一特例 老板 → boss", anchors["老板"] === "boss", String(anchors["老板"]));
  const obDerived = await onboard({ by: "codex-看板编辑", approval: "老板 口述", name: "codex-甲" });
  const obDerivedBody = await obDerived.json().catch(() => ({}));
  check(
    "入职：不给工号时按契约派生（codex-甲 → codex-d0e43b）",
    obDerived.status === 200 && obDerivedBody.slug === "codex-d0e43b",
    JSON.stringify(obDerivedBody).slice(0, 120)
  );

  // ⑫ HUB-006 暂停闸：置闸 → 非老板解除无效 → 老板公告解除
  const haltSet = await fetch(base + "/api/halt", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ by: "codex-测在岗", severity: "S1", reason: "自测：引擎异常" }),
  });
  const haltJson = async () => ((await (await fetch(base + "/api/dialog?limit=50", { headers: hdr })).json()).halt || {});
  const h1 = await haltJson();
  check("暂停闸：置闸成功且状态可见", haltSet.status === 200 && h1.halted === true && h1.severity === "S1", JSON.stringify(h1).slice(0, 120));
  check("暂停闸：看板出现「已暂停 · 等老板」", /【已暂停 · 等老板】/.test(boardLines().join("\n")), "red bar");
  const wokenBeforeHalt = (childLog.match(/DELIVERED\+WOKEN/g) || []).length;
  await fetch(base + "/api/send", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ target: "codex-测在岗", message: "[自测] 暂停期间不该被自动唤醒", author: "dsh-老员工" }),
  });
  await new Promise((r) => setTimeout(r, 4000));
  check(
    "暂停闸：暂停期间不自动唤醒（别的线的投递只落信箱）",
    /HALT: 暂停中，只落信箱不唤醒/.test(childLog) &&
      (childLog.match(/DELIVERED\+WOKEN/g) || []).length === wokenBeforeHalt,
    "gated"
  );
  await fetch(base + "/api/send", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ target: "全体", message: "【解除暂停】我觉得可以了", author: "codex-测在岗" }),
  });
  await new Promise((r) => setTimeout(r, 2500));
  const h2 = await haltJson();
  check("暂停闸：**非老板**发的『解除暂停』不生效", h2.halted === true, JSON.stringify(h2).slice(0, 90));
  check("暂停闸：越权解除会被明确回绝", /不生效/.test(boardLines().join("\n")), "rejected");
  await fetch(base + "/api/send", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ target: "全体", message: "【解除暂停】已处理完，继续干活。", author: "老板" }),
  });
  await new Promise((r) => setTimeout(r, 3000));
  const h3 = await haltJson();
  check("暂停闸：老板的公告解除生效（状态清 + 有 resumedAt）", h3.halted === false && !!h3.resumedAt, JSON.stringify(h3).slice(0, 120));
  check(
    "暂停闸：恢复文案不写『已通知全员』（诚实口径）",
    /【已恢复 · 老板/.test(boardLines().join("\n")) && !/已通知全员/.test(boardLines().join("\n")),
    "honest"
  );

  // ⑬ HUB-007 实时通道（SSE）
  const sseAbort = new AbortController();
  const sseRes = await fetch(base + "/api/events", { signal: sseAbort.signal });
  check(
    "SSE：/api/events 返回 text/event-stream（不要求 token）",
    /text\/event-stream/.test(String(sseRes.headers.get("content-type") || "")),
    String(sseRes.headers.get("content-type") || "")
  );
  const sseReader = sseRes.body.getReader();
  const firstChunk = await sseReader.read();
  check(
    "SSE：连上就先给一行（retry/注释）",
    /retry:|: connected/.test(Buffer.from(firstChunk.value || []).toString("utf8")),
    "hello"
  );
  const t0sse = Date.now();
  await fetch(base + "/api/send", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ target: "老板", message: "[自测] SSE：这条应当触发一次 changed", author: "老板" }),
  });
  let sseGot = false;
  let sseBuf = "";
  const sseDeadline = Date.now() + 8000;
  while (Date.now() < sseDeadline && !sseGot) {
    const { value, done } = await sseReader.read();
    if (done) break;
    sseBuf += Buffer.from(value || []).toString("utf8");
    if (/event: changed/.test(sseBuf)) sseGot = true;
  }
  const sseMs = Date.now() - t0sse;
  sseAbort.abort();
  check("SSE：有新记录时推 changed（不再等 5 秒轮询）", sseGot, sseMs + "ms");

  // ⑭ HUB-008 任务表 / 建卡 / 状态流转
  const tasks0 = await (await fetch(base + "/api/tasks", { headers: hdr })).json();
  check(
    "任务表：卡 + 派单合成一张表，并按前缀分组",
    tasks0.ok === true && tasks0.count >= 2 && Number(tasks0.byProject.HUB) >= 1 && Number(tasks0.byProject.KIT) >= 1,
    JSON.stringify(tasks0.byProject || {}).slice(0, 120)
  );
  const made = await fetch(base + "/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({
      author: "codex-看板编辑",
      assignee: "codex-测无会话",
      prefix: "HUB",
      title: "自测建卡：把任务接口打通",
      acceptance: ["GET /api/tasks 能看到这张卡", "状态能流转并留痕"],
    }),
  });
  const madeBody = await made.json();
  check(
    "建卡：自动取号 + 落标准卡（HUB-902）",
    made.status === 200 && madeBody.id === "HUB-902" && fs.existsSync(path.join(dirs.tasks, "HUB-902.md")),
    JSON.stringify(madeBody).slice(0, 120)
  );
  // ★ HUB-004 §四之一（总监 2026-09-11 05:4x）：提交后必须**立刻**给出这条单的投递结论（三态），
  //   不许只回一句"提交成功"——否则老板分不清这单是"有人接"还是"压在信箱里"。
  const dv = madeBody.delivery || {};
  check(
    "HUB-004：派单回应带三态投递结论（woken / not-woken / mailbox）",
    ["woken", "not-woken", "mailbox"].indexOf(String(dv.status)) >= 0 && String(dv.text || "").length > 0,
    JSON.stringify(dv).slice(0, 150)
  );
  check(
    "HUB-004：接手方没绑定会话时，结论**不许**写「已叫醒」（不谎报）",
    dv.status === "mailbox" && !/已叫醒/.test(String(dv.text || "")),
    String(dv.status) + " / " + String(dv.text || "").slice(0, 70)
  );
  const taskLine = fs
    .readFileSync(BOARD_FILE, "utf8")
    .split("\n")
    .find((l) => l.indexOf("HUB-902") >= 0 && l.indexOf("派单") >= 0) || "";
  check(
    "HUB-004：看板留的派单记录里写了**谁派的**（署名归发起线，不冒充老板）",
    taskLine.indexOf("@codex-看板编辑") >= 0 && taskLine.indexOf("@codex-测无会话") >= 0,
    taskLine.slice(0, 150)
  );
  const noAccept = await fetch(base + "/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ author: "codex-看板编辑", assignee: "codex-测无会话", prefix: "HUB", title: "没有验收标准的单" }),
  });
  check("建卡：**没有验收标准不许派**（400）", noAccept.status === 400, "status=" + noAccept.status);
  const badPrefix = await fetch(base + "/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ author: "codex-看板编辑", assignee: "codex-测无会话", prefix: "XX", title: "前缀没登记", acceptance: ["x"] }),
  });
  check("建卡：前缀不在登记表被拒（400）", badPrefix.status === 400, "status=" + badPrefix.status);
  const badWho = await fetch(base + "/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ author: "codex-看板编辑", assignee: "codex-不存在", prefix: "HUB", title: "接手方没注册", acceptance: ["x"] }),
  });
  check("建卡：接手方没注册被拒（400）", badWho.status === 400, "status=" + badWho.status);
  const st1 = await fetch(base + "/api/tasks/status", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ id: "HUB-902", state: "done", by: "codex-看板编辑", note: "自测通过" }),
  });
  const tasks1 = await (await fetch(base + "/api/tasks", { headers: hdr })).json();
  const rec902 = (tasks1.tasks || []).find((t) => t.id === "HUB-902");
  check(
    "状态流转：写侧车、任务表里可见（带 by/at）",
    st1.status === 200 && rec902 && rec902.state === "done" && rec902.by === "codex-看板编辑" && /T/.test(String(rec902.at || "")),
    JSON.stringify(rec902 || {}).slice(0, 130)
  );
  // 连带修复（HUB-016 顺带抓到）：手机派单页署「老板」，而 `/api/tasks` 原来只认注册名 →
  //   一律 400 —— **页面看着做好了、其实一条都派不出去**。这里放在 HUB-902 之后**真提交一次**，
  //   既不抢号，也把"端到端能跑"钉住（教训：代码在 main 里 ≠ 端到端能跑）。
  const taskAsBoss = await fetch(base + "/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({
      author: "老板",
      assignee: "codex-测无会话",
      prefix: "HUB",
      title: "自测HUB-016：手机派单页署老板",
      acceptance: ["能从手机页的署名路径提交成功"],
    }),
  });
  const taskAsBossBody = await taskAsBoss.json().catch(() => ({}));
  check(
    "HUB-016 连带：手机派单页署「老板」能提交（原来 400，端到端才抓得到）",
    taskAsBoss.status === 200 && taskAsBossBody.ok === true,
    JSON.stringify(taskAsBossBody).slice(0, 120)
  );

  // ⑮ HUB-010 群组：注入接口（幂等 upsert）+ 校验
  const g0 = await (await fetch(base + "/api/groups", { headers: hdr })).json();
  check("群组：初始为空（且接口可用）", g0.ok === true && g0.count === 0, "count=" + g0.count);
  const gPost = async (p) => {
    const rr = await fetch(base + "/api/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...hdr },
      body: JSON.stringify(p),
    });
    return { status: rr.status, body: await rr.json() };
  };
  const g1 = await gPost({ name: "看板基建", members: ["codex-看板编辑", "codex-唤醒通道", "codex-看板服务"], by: "codex-总监", source: "自测中间件" });
  check(
    "群组：注入成功（幂等 upsert，返回 id/created）",
    g1.status === 200 && g1.body.ok === true && g1.body.created === true && /^g-/.test(g1.body.id),
    JSON.stringify(g1.body).slice(0, 120)
  );
  const g2 = await gPost({ name: "看板基建", members: ["codex-看板编辑"], by: "codex-总监", source: "自测中间件" });
  check(
    "群组：同名字再注入 = 更新（created=false，不产生重复群）",
    g2.status === 200 && g2.body.created === false && g2.body.id === g1.body.id,
    JSON.stringify(g2.body).slice(0, 90)
  );
  const gBad = await gPost({ name: "空群", members: ["没注册的线"], by: "codex-总监" });
  check("群组：成员必须已注册（400）", gBad.status === 400, "status=" + gBad.status);
  const gBadBy = await gPost({ name: "匿名群", members: ["codex-看板编辑"], by: "路人" });
  check("群组：注入方必须实名（400）", gBadBy.status === 400, "status=" + gBadBy.status);
  const dj = await (await fetch(base + "/api/dialog?limit=20", { headers: hdr })).json();
  check(
    "群组：/api/dialog 下发给页面（带头像）",
    Array.isArray(dj.groups) && dj.groups.length === 1 && dj.groups[0].name === "看板基建" && !!dj.groups[0].avatar,
    JSON.stringify((dj.groups || [])[0] || {}).slice(0, 120)
  );

  // ⑯ 队列冷却语义（2026-09-12 01:0x 老板发现两条消息被"阻塞"）：
  //    **不同内容**的消息不该被冷却挡住（能连着叫醒）；**同一条**才必须去重。
  // 用 /api/mail{wake:true} 直接看"这次到底有没有真的叫醒"，避免被后台唤醒（公告/解除暂停的扇出）干扰计数
  const mailWake = async (body) =>
    (await (await fetch(base + "/api/mail", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...hdr },
      body: JSON.stringify({ to: "codex-测窗口", from: "老板", body: body, wake: true }),
    })).json());
  const q1 = await mailWake("[自测] 连发第一条：内容不同，该唤醒");
  const q2 = await mailWake("[自测] 连发第二条：内容不同，也该唤醒");
  check(
    "队列：内容不同的连续消息**不会被冷却挡住**（不再「阻塞」）",
    q1.woke === true && q2.woke === true,
    JSON.stringify({ q1: q1, q2: q2 }).slice(0, 140)
  );
  const dupBody = "[自测] 同一条消息，连投两次应当只叫一次";
  const q3 = await mailWake(dupBody);
  const q4 = await mailWake(dupBody);
  check(
    "队列：**同一条消息**十分钟内不重复投（幂等，接口直接报 deduped）",
    q3.woke === true && q4.deduped === true && q4.woke === false,
    JSON.stringify({ q3: q3, q4: q4 }).slice(0, 140)
  );

  // ⑰ HUB-011 可塑性：能力协商 / 增量游标 / 服务端已读 / schema
  const meta = await (await fetch(base + "/api/meta", { headers: hdr })).json();
  check(
    "能力协商：/api/meta 不需要 token，且给出 apiVersion/features/schemas",
    meta.ok === true && meta.apiVersion === "2" && Array.isArray(meta.features) && meta.features.length >= 5 && !!meta.schemas.dialog,
    "api=" + meta.apiVersion + " features=" + (meta.features || []).length
  );
  const dNow = await (await fetch(base + "/api/dialog?limit=50", { headers: hdr })).json();
  const cur = dNow.cursor || {};
  check(
    "增量游标：/api/dialog 带回 oldestId/newestId/total（客户端据此增量拉）",
    !!cur.oldestId && !!cur.newestId && Number(cur.total) > 0,
    JSON.stringify(cur).slice(0, 120)
  );
  const dSince = await (await fetch(base + "/api/dialog?since=" + encodeURIComponent(cur.oldestId) + "&limit=500", { headers: hdr })).json();
  check(
    "增量游标：since 只回这条之后的新记录",
    Array.isArray(dSince.records) && dSince.records.length > 0 && dSince.records.every((r) => String(r.id) !== cur.oldestId),
    "since→" + dSince.records.length + " 条"
  );
  const dBefore = await (await fetch(base + "/api/dialog?before=" + encodeURIComponent(cur.newestId) + "&limit=5", { headers: hdr })).json();
  check(
    "增量游标：before 可以往回翻历史（分页）",
    Array.isArray(dBefore.records) && dBefore.records.length > 0 && dBefore.records.every((r) => String(r.id) !== cur.newestId),
    "before→" + dBefore.records.length + " 条"
  );
  const rd = await fetch(base + "/api/read", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ deviceId: "dev-selftest", upToId: cur.newestId }),
  });
  check("多设备地基：POST /api/read 记录本设备游标", rd.status === 200, "status=" + rd.status);
  check(
    "schema 版本：tasks_state / halt / boss_events 都带版本标记",
    (() => {
      const f = path.join(dirs.data, "..", "mailbox", "tasks_state.json");
      try {
        const o = JSON.parse(fs.readFileSync(f, "utf8"));
        return o.schema === "tasks_state.v1" || (o.tasks && o.schema === "tasks_state.v1");
      } catch {
        return false;
      }
    })(),
    "tasks_state.v1"
  );

  // ⑱ HUB-012 承载层：员工 / 物料·时间轴 / 多来源归一
  const emp = await (await fetch(base + "/api/employees", { headers: hdr })).json();
  check(
    "员工：/api/employees 给出四级/权限/插槽/运行态（对齐套件员工卡）",
    emp.ok === true && emp.count >= 5 && !!emp.byLevel && typeof emp.employees[0].level === "string" &&
      Array.isArray(emp.employees[0].avatar ? [1] : []),
    "count=" + emp.count + " levels=" + JSON.stringify(emp.byLevel)
  );
  const itAdd = await fetch(base + "/api/items", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ by: "codex-看板编辑", project: "HUB", line: "主线", kind: "node", title: "自测：承载层物料节点", tags: ["自测"] }),
  });
  const itBody = await itAdd.json();
  check("物料/节点：能写入时间轴", itAdd.status === 200 && itBody.ok === true && !!itBody.item.id, JSON.stringify(itBody).slice(0, 110));
  const itList = await (await fetch(base + "/api/items?project=HUB", { headers: hdr })).json();
  check(
    "物料/节点：能按项目查时间轴（带 kind 计数）",
    itList.ok === true && itList.count >= 1 && Number(itList.byKind.node) >= 1,
    "count=" + itList.count + " " + JSON.stringify(itList.byKind)
  );
  const itBad = await fetch(base + "/api/items", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ by: "路人", project: "HUB", title: "匿名物料" }),
  });
  check("物料/节点：署名必须实名（400）", itBad.status === 400, "status=" + itBad.status);
  const ing = await fetch(base + "/api/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ source: "selftest-txt", ref: "/tmp/a.txt", from: "codex-看板编辑", body: "自测：多来源归一（txt 来源的一条）" }),
  });
  const ingBody = await ing.json();
  check("多来源归一：任意来源进来都是同一种记录（channel=ingest）", ing.status === 200 && ingBody.ok === true && ingBody.added === true, JSON.stringify(ingBody).slice(0, 110));
  const dIng = await (await fetch(base + "/api/dialog?limit=50", { headers: hdr })).json();
  check(
    "多来源归一：记录里带 source/ref（能追溯它从哪来）",
    (dIng.records || []).some((r) => r.channel === "ingest" && r.refs && r.refs.source === "selftest-txt" && r.refs.ref === "/tmp/a.txt"),
    "ingest record"
  );
  const ingAnon = await fetch(base + "/api/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ source: "x", from: "匿名", body: "不许匿名" }),
  });
  check("多来源归一：来源可以不同，但**署名不能匿名**（400）", ingAnon.status === 400, "status=" + ingAnon.status);

  // ⑲ 投信箱的"顺便叫醒"开关（老板 2026-09-12 指出：投完没叫醒=等于没投）
  const mDefault = await (await fetch(base + "/api/mail", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ to: "codex-测窗口", from: "老板", body: "[自测] 默认只投不唤醒" }),
  })).json();
  check("投信箱默认：只投不唤醒（I3 语义不变）", mDefault.ok === true && mDefault.woke === false, JSON.stringify(mDefault));
  const mWake = await (await fetch(base + "/api/mail", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...hdr },
    body: JSON.stringify({ to: "codex-测窗口", from: "老板", body: "[自测] 这条要顺便叫醒", wake: true }),
  })).json();
  check("投信箱 wake:true：顺手叫醒（queue 优先）", mWake.ok === true && mWake.woke === true, JSON.stringify(mWake));

  // ⑳ 公告重做（2026-09-12）：**每条公告单独回执**（取消笼统式）+ 短号 + 公告投信箱
  const noticeLine = "- @全体 " + boardStamp(new Date()) + " 老板：自测公告：请回执";
  fs.appendFileSync(BOARD_FILE, noticeLine + "\n", "utf8");
  await new Promise((r) => setTimeout(r, 3000));
  const dn = await (await fetch(base + "/api/dialog?limit=50", { headers: hdr })).json();
  const noticeRec = (dn.records || []).filter((r) => r.kind === "notice").pop();
  const ncode = noticeRec ? "N-" + String(noticeRec.id).slice(0, 4).toUpperCase() : "";
  check("公告：入库并带短号可算", !!noticeRec && /^N-[0-9A-Z]{4}$/.test(ncode), ncode);
  check(
    "公告：发布后投到各线信箱（不再是「只入库」）",
    fs.existsSync(path.join(dirs.mailbox, "pending_codex-awake2.ndjson")) &&
      fs.readFileSync(path.join(dirs.mailbox, "pending_codex-awake2.ndjson"), "utf8").includes(ncode),
    "mailbox has " + ncode
  );
  // 回执：**裸词不算**（取消笼统式），**带短号才算**
  fs.appendFileSync(BOARD_FILE, "- @老板 " + boardStamp(new Date()) + " codex-测无会话：收到\n", "utf8");
  await new Promise((r) => setTimeout(r, 2500));
  const d1 = await (await fetch(base + "/api/dialog?limit=50", { headers: hdr })).json();
  const n1 = (d1.records || []).filter((r) => r.kind === "notice").pop();
  // ★ 口径变更（老板 2026-09-13 04:0x）：**裸词「收到」现在算**——按记录顺序销它之前最近一条未回执的公告（mode=bare）。
  //   所以这条用例从"不算"翻转成"算"，并钉住 mode。
  check(
    "公告回执：裸词「收到」也算（老板 04:0x 新口径，mode=bare）",
    !!((n1.refs.acks || {})["codex-测无会话"] || {}).mode,
    JSON.stringify((n1.refs.acks || {})["codex-测无会话"] || {})
  );
  fs.appendFileSync(BOARD_FILE, "- @老板 " + boardStamp(new Date()) + " codex-测无会话：收到 " + ncode + "\n", "utf8");
  await new Promise((r) => setTimeout(r, 2500));
  const d2 = await (await fetch(base + "/api/dialog?limit=50", { headers: hdr })).json();
  const n2 = (d2.records || []).filter((r) => r.kind === "notice").pop();
  check(
    "公告回执：带短号「收到 " + ncode + "」才算",
    !!((n2.refs.acks || {})["codex-测无会话"] || {}).mode && (n2.refs.acks["codex-测无会话"].mode === "code" || n2.refs.acks["codex-测无会话"].mode === "quote"),
    JSON.stringify(n2.refs.acks || {}).slice(0, 120)
  );
  check(
    "公告回执：未收到的线在 pendingAck 里（界面据此显示「未收到」）",
    Array.isArray(n2.refs.pendingAck) && !n2.refs.pendingAck.includes("codex-测无会话"),
    "pending=" + JSON.stringify(n2.refs.pendingAck || [])
  );

  // ㉑ HUB-015 公告"送到"补全（`codex-修复` 2026-09-13 01:54 反馈；总监派单）
  //   ① 入职时补投**生效公告正文**；② 回执窗口从**投递时刻**起算（入职晚于发布也要回执）；
  //   ③ 在册但没 threadId 的条目不进 pendingAck（不再空催 + 不再上板噪声）
  //   TTL 已在本轮启动时调到 9 秒（见 spawn env），才能把"入职晚于发布"压缩进自测时限。
  const notice15 = "- @全体 " + boardStamp(new Date()) + " 老板：自测HUB015：这条专门用来验回执窗口";
  fs.appendFileSync(BOARD_FILE, notice15 + "\n", "utf8");
  await new Promise((r) => setTimeout(r, 2500)); // 等入库 + 扇出（投信箱并记下投递时刻）
  const d15 = await (await fetch(base + "/api/dialog?limit=500", { headers: hdr })).json();
  const n15 = (d15.records || []).filter((r) => r.kind === "notice" && /自测HUB015/.test(String(r.body || ""))).pop();
  const code15 = n15 ? "N-" + String(n15.id).slice(0, 4).toUpperCase() : "";
  check("HUB-015①：公告已入库", !!n15 && !!code15, code15);
  // 入职一条**晚于发布**的新线（此刻公告还"生效中"：TTL 9s，刚过 2.5s）
  const ob15 = await onboard({
    by: "codex-看板编辑",
    approval: "老板 自测口述",
    name: "codex-测补投",
    slug: "codex-backfill",
    threadId: "01a04444-0000-7000-8000-000000000009",
  });
  const ob15Body = await ob15.json().catch(() => ({}));
  const bfMailFile = path.join(dirs.mailbox, "pending_codex-backfill.ndjson");
  const bfMail = fs.existsSync(bfMailFile) ? fs.readFileSync(bfMailFile, "utf8") : "";
  check(
    "HUB-015①：入职时把生效公告的**正文**补投进新线信箱",
    ob15.status === 200 && Number(ob15Body.noticesDelivered || 0) >= 1 && bfMail.includes("【公告 " + code15) && bfMail.includes("验回执窗口"),
    "noticesDelivered=" + ob15Body.noticesDelivered
  );
  // 等到公告**全局过期**（TTL 9s，发布后约 10.5s）再看：老线窗口已关，新线窗口还开着
  await new Promise((r) => setTimeout(r, 8000));
  const d15b = await (await fetch(base + "/api/dialog?limit=500", { headers: hdr })).json();
  const n15b = (d15b.records || []).filter((r) => r.kind === "notice" && /自测HUB015/.test(String(r.body || ""))).pop();
  const pend15 = (n15b && n15b.refs && n15b.refs.pendingAck) || [];
  check("HUB-015②：这条公告对全局已过期（expired=true）", !!n15b && n15b.refs.expired === true, JSON.stringify(n15b && n15b.refs.expired));
  check(
    "HUB-015②：**入职晚于发布**的新线仍在待回执里（窗口从投递给它的时刻起算）",
    pend15.includes("codex-测补投") && n15b.refs.active === true,
    "pending=" + JSON.stringify(pend15)
  );
  check(
    "HUB-015②：发布时就收到的老线，窗口已关（不再挂着）",
    !pend15.includes("codex-测窗口"),
    "pending=" + JSON.stringify(pend15)
  );
  check(
    "HUB-015③：在册但**没 threadId** 的条目不进 pendingAck（dsh-老员工/测无会话不再空催）",
    !pend15.includes("dsh-老员工") && !pend15.includes("codex-测无会话"),
    "pending=" + JSON.stringify(pend15)
  );

  // ★ HUB-018 E（老板 04:0x 定）：**回执只回「收到」两个字**——按记录顺序销掉该线**最近一条未回执**的公告。
  //   判别性：连发两条公告、只回一句裸「收到」→ 必须销**后**那条（B），且**不许**把前一条（A）也销掉。
  // 注意：**发一条就读一条**——测试环境热文件轮转凶（4000B/10 行），发完两条再读会被归档出热文件（我先前就这样扑空过）
  const getE = async (kw) => {
    const d = await (await fetch(base + "/api/dialog?limit=500", { headers: hdr })).json();
    return (d.records || []).filter((r) => r.kind === "notice" && String(r.body || "").indexOf(kw) >= 0).pop();
  };
  fs.appendFileSync(BOARD_FILE, "- @全体 " + boardStamp(new Date()) + " 老板：E测公告A（先发）\n", "utf8");
  await new Promise((r) => setTimeout(r, 2600));
  const nEa = await getE("E测公告A");
  fs.appendFileSync(BOARD_FILE, "- @全体 " + boardStamp(new Date()) + " 老板：E测公告B（后发）\n", "utf8");
  await new Promise((r) => setTimeout(r, 2600));
  const nEb0 = await getE("E测公告B");
  fs.appendFileSync(BOARD_FILE, "- @老板 " + boardStamp(new Date()) + " codex-测在岗：收到\n", "utf8");
  await new Promise((r) => setTimeout(r, 2600));
  check("E①：两条公告都能读到（发一条读一条，避开轮转）", !!nEa && !!nEb0, (nEa ? "A ok" : "A 缺") + " / " + (nEb0 ? "B ok" : "B 缺"));
  const nEb = await getE("E测公告B");
  check(
    "E：只回「收到」两个字 → 销的是**最近那条**公告（mode=bare）",
    !!nEb && !!((nEb.refs.acks || {})["codex-测在岗"] || {}).mode,
    JSON.stringify((nEb && nEb.refs.acks) || {})
  );
  const nEa2 = await getE("E测公告A");
  check(
    "E：更早那条公告**不被误销**（一句「收到」只销一条）",
    !!nEa2 && !((nEa2.refs.acks || {})["codex-测在岗"]),
    JSON.stringify((nEa2 && nEa2.refs.acks) || {})
  );

  // ★ HUB-018 追加（老板 2026-09-13 04:5x 定）：**推送记账**
  //   痛点：同一封信被叫两次（① /api/mail 的"来信提示"带正文 ② crew_host 30 秒门铃只报条数）。
  //   口径：**推成功就记一行**进 pushed.ndjson（给门铃算未读水位）；推失败/写失败都不许影响投递。
  //   判别性：同一次「推得通」+「推不通」各来一发，账本**只许**出现前者。
  const pushedPath = path.join(path.dirname(DIALOG_FILE), "pushed.ndjson");
  const readLedger = () =>
    fs.existsSync(pushedPath) && fs.statSync(pushedPath).isFile()
      ? fs
          .readFileSync(pushedPath, "utf8")
          .split("\n")
          .filter(Boolean)
          .map((s) => {
            try {
              return JSON.parse(s);
            } catch {
              return null; // 解析侧宽容：坏行跳过，不许炸调用方
            }
          })
      : [];
  const ledgerBefore = readLedger().length;
  const pushMail = (to, body) =>
    fetch(base + "/api/mail", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...hdr },
      body: JSON.stringify({ to, from: "codex-测在岗", body, wake: true }),
    }).then((r) => r.json());
  const pushOk = await pushMail("codex-测窗口", "[自测] 推送记账：这条推得通（桩返回 0）");
  const pushBad = await pushMail("codex-测在岗", "[自测] 推送记账：这条推不通（桩返回 1）");
  const delta = readLedger().slice(ledgerBefore);
  check(
    "推送记账：推成功写一行（by=hub / to=看板名 / ts_ms / mailbox_ts 齐）",
    delta.some(
      (r) =>
        r &&
        r.to === "codex-测窗口" &&
        r.by === "hub" &&
        Number.isFinite(r.ts_ms) &&
        !!r.mailbox_ts &&
        /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(String(r.ts))
    ),
    "pushOk=" + JSON.stringify(pushOk) + " delta=" + JSON.stringify(delta)
  );
  check(
    "推送记账：推失败**不写**（这正是门铃兜底要叫的场景）",
    pushBad.woke !== true && !delta.some((r) => r && r.to === "codex-测在岗"),
    "woke=" + pushBad.woke + " delta=" + JSON.stringify(delta.map((r) => r && r.to))
  );
  // 写失败不许影响投递：把账本路径临时换成"目录"→ append 必然抛 → 只在日志记一笔，投递**仍须成功**。
  let pushNoLedger = null;
  try {
    fs.rmSync(pushedPath, { force: true });
    fs.mkdirSync(pushedPath, { recursive: true });
    pushNoLedger = await pushMail("codex-测窗口", "[自测] 推送记账：账本写不进去，投递也不许失败");
  } finally {
    try {
      fs.rmdirSync(pushedPath);
    } catch {}
  }
  const pingOk = await (await fetch(base + "/api/ping")).json().catch(() => ({}));
  check(
    "推送记账：账本写失败**不许影响投递**（只多叫一次门铃）",
    pushNoLedger && pushNoLedger.ok === true && pushNoLedger.woke === true && pingOk.ok === true,
    JSON.stringify(pushNoLedger)
  );

  child.kill();
  await new Promise((res) => setTimeout(res, 500));

  const failed = results.filter((x) => !x.ok);
  process.stdout.write("\n自测结果：" + (results.length - failed.length) + "/" + results.length + " 通过\n");
  if (failed.length && serverLog) process.stdout.write("--- 服务日志尾部 ---\n" + serverLog.slice(-1500) + "\n");
  return failed.length ? 1 : 0;
}

let code = 1;
let childRef = null;
let childLog = "";
try {
  code = await main();
} catch (e) {
  process.stdout.write("自测异常：" + (e && e.stack) + "\n");
  if (childLog) process.stdout.write("--- 临时服务日志（异常时也要看）---\n" + childLog.slice(-1200) + "\n");
  code = 1;
} finally {
  // 无论成功失败都要收掉临时服务：否则异常路径会留下占端口的孤儿进程
  try {
    if (childRef) childRef.kill();
  } catch {}
  try {
    fs.rmSync(ROOT, { recursive: true, force: true });
  } catch {}
}
process.exit(code);
