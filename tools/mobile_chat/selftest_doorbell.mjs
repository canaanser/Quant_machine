#!/usr/bin/env node
/**
 * PLT-007 自测：门铃守卫（可复跑、无外部依赖）
 * 跑法：node tools/mobile_chat/selftest_doorbell.mjs
 * 造一个**桩服务**顶替 dsh web，逐条验守卫；用临时 state/信箱，不碰真数据。
 */

import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const TOOL = path.join(HERE, "dsh_doorbell.mjs");
const SESSION = "session-selftest-0001";

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "doorbell-selftest-"));
const STATE = path.join(tmp, "state.json");
const MAILBOX = path.join(tmp, "mailbox.ndjson");
const BODY = path.join(tmp, "body.txt");
fs.writeFileSync(BODY, "自测正文：请只回一行 OK\n", "utf8");
const WEBLOG = path.join(tmp, "weblog.log");
fs.writeFileSync(WEBLOG, "dsh web: http://127.0.0.1:3080/?token=STUBTOKENVALUE\n", "utf8");
const NO_LOG = path.join(tmp, "no-such.log");

// 与工具同口径：本地日期（不用 toISOString，那是 UTC）
const localDay = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

let mode = "ok";
let updatedAt = 1000;
let promptHits = 0;
let remints = 0;

const server = http.createServer((req, res) => {
  const send = (code, obj) => {
    res.writeHead(code, { "content-type": "application/json" });
    res.end(JSON.stringify(obj));
  };
  if (req.url.startsWith("/?token=")) {
    remints += 1;
    res.writeHead(303, { "set-cookie": "dsh-auth-test=stub; Path=/" });
    return res.end();
  }
  let body = "";
  req.on("data", (c) => (body += c));
  req.on("end", () => {
    const env = JSON.parse(body || "{}");
    if (env.method === "session/prompt") {
      promptHits += 1;
      if ((mode === "401" && promptHits === 1) || mode === "401-always") {
        return send(401, { error: "unauthorized" });
      }
      if (mode === "500") return send(500, { error: "boom" });
      updatedAt += 1;
      return send(200, { result: { ok: true, value: { accepted: true } } });
    }
    if (env.method === "session/list") {
      return send(200, {
        result: { ok: true, value: { items: [{ sessionId: SESSION, updatedAt, cwd: "/x", projections: { values: { title: "stub" } } }] } },
      });
    }
    send(404, { error: "no route" });
  });
});

// ★ 必须异步 spawn：桩服务跑在本进程里，spawnSync 会堵死事件循环 → 子进程请求永远挂死。
const run = (extra = [], envExtra = {}) =>
  new Promise((resolve) => {
    const child = spawn(process.execPath, [TOOL, "--file", BODY, "--session", SESSION, ...extra], {
      env: {
        ...process.env,
        DSH_DOORBELL_BASE: `http://127.0.0.1:${server.address().port}`,
        DSH_DOORBELL_STATE: STATE,
        DSH_DOORBELL_MAILBOX: MAILBOX,
        DSH_DOORBELL_COOKIE: path.join(tmp, "cookie.txt"),
        DSH_DOORBELL_WEBLOG: WEBLOG,
        ...envExtra,
      },
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (c) => (stdout += c));
    child.stderr.on("data", (c) => (stderr += c));
    child.on("close", (status) => resolve({ status, stdout, stderr }));
  });

const results = [];
const check = (name, pass, detail = "") => {
  results.push({ name, pass, detail });
  console.log(`${pass ? "PASS" : "FAIL"}  ${name}${detail ? "  -> " + detail : ""}`);
};

await new Promise((r) => server.listen(0, "127.0.0.1", r));

// ① 成功 + 验证到回合
let out = await run();
check(
  "成功注入并验证到 updatedAt 变化",
  out.status === 0 && /已验证/.test(out.stdout),
  `exit=${out.status} out=${JSON.stringify((out.stdout || "").trim().slice(0, 160))} err=${JSON.stringify((out.stderr || "").trim().slice(0, 200))}`,
);

// ② 同内容 10 分钟内重发 → 跳过
out = await run();
check("同内容 10 分钟内不重发", /跳过/.test(out.stdout) && promptHits === 1, `promptHits=${promptHits}`);

// ③ --force 可强制再发
out = await run(["--force"]);
check("--force 可强制重发", /注入 accepted/.test(out.stdout), out.stdout.trim().split("\n")[0]);

// ④ 日限流
fs.writeFileSync(STATE, JSON.stringify({ day: localDay(), count: 20, sent: {} }));
out = await run(["--force"]);
check("日限流生效", /已达上限/.test(out.stdout), out.stdout.trim());

// ⑤ 401 → 重换 cookie 后重试成功（重试间隔 ≥2s）
fs.rmSync(STATE, { force: true });
mode = "401";
promptHits = 0;
const t0 = Date.now();
out = await run();
const elapsed = Date.now() - t0;
check("401 自动重换 cookie 并重试成功", out.status === 0 && remints === 1 && promptHits === 2, `remints=${remints} hits=${promptHits}`);
check("重试间隔 ≥2s", elapsed >= 2000, `${elapsed}ms`);

// ⑥ 换 cookie 也失败（无日志）→ 兜底回投信箱
fs.rmSync(STATE, { force: true });
mode = "401-always";
promptHits = 0;
out = await run([], { DSH_DOORBELL_WEBLOG: NO_LOG });
const mail = fs.existsSync(MAILBOX) ? fs.readFileSync(MAILBOX, "utf8") : "";
check("失败兜底回投 pending_dsh-main", out.status === 1 && /门铃失败/.test(mail), `status=${out.status} mail=${mail.length}B`);

// ⑦ 缺 --file → 直接拒发（exit 2）
out = spawnSync(process.execPath, [TOOL], { encoding: "utf8" });
check("缺 --file 直接拒发", out.status === 2, `exit=${out.status}`);

// ⑧ --dry 不注入
fs.rmSync(STATE, { force: true });
const hitsBefore = promptHits;
out = await run(["--dry"]);
check("--dry 不真发", /\[dry\]/.test(out.stdout) && promptHits === hitsBefore, out.stdout.trim());

server.close();
const failed = results.filter((r) => !r.pass);
console.log(`\n自测结果：${results.length - failed.length}/${results.length} 通过`);
if (failed.length) {
  console.log("失败项：" + failed.map((f) => f.name).join("；"));
  process.exit(1);
}
console.log(`临时目录（可留证）：${tmp}`);
