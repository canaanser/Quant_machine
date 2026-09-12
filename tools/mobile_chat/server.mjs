import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import os from "node:os";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const CODEX = "C:\\Users\\Administrator\\AppData\\Local\\OpenAI\\Codex\\bin\\fd4c151a749f3ab4\\codex.exe";
const WORKSPACE = "E:\\stockgate\\Quant_Alpha_System";
const HOST = process.env.MCHAT_HOST || "100.64.75.72";
const PORT = Number(process.env.MCHAT_PORT || 8787);
const DATA_DIR = process.env.MCHAT_DATA || path.join(os.homedir(), ".codex", "mobile_chat");
const TURN_TIMEOUT_MS = Number(process.env.MCHAT_TIMEOUT_MS || 600000);

const TOKEN_FILE = path.join(DATA_DIR, "token.txt");
const STATE_FILE = path.join(DATA_DIR, "state.json");
const LAST_FILE = path.join(DATA_DIR, "last.txt");
const LOG_FILE = path.join(DATA_DIR, "log.txt");

const PERSONA =
  "（手机通道）你是本仓库的 Codex：主审阅 / 架构 / 调度，负责代码规范与质量把关。老板正通过手机跟你聊天。请遵守仓库 AGENTS.md 里的角色与纪律；回答用中文，先给结论再展开，尽量简洁。此通道当前为只读模式：除非老板明确要求，不要修改或删除任何文件，不要执行任何 git 写操作。可先按需阅读 AGENTS.md 指定的交接文档来恢复上下文。";

let busy = false;
let shutdown = false;

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

async function getToken() {
  ensureDataDir();
  try {
    const t = fs.readFileSync(TOKEN_FILE, "utf8").trim();
    if (t.length >= 16) return t;
  } catch {}
  const token = crypto.randomBytes(24).toString("hex");
  fs.writeFileSync(TOKEN_FILE, token, { mode: 0o600 });
  log("NEW TOKEN CREATED");
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

function parseThreadId(stdout) {
  for (const line of stdout.split("\n")) {
    const s = line.trim();
    if (!s.startsWith("{")) continue;
    try {
      const ev = JSON.parse(s);
      if (ev.type === "thread.started" && ev.thread_id) return String(ev.thread_id);
    } catch {}
  }
  return null;
}

function runCodex(args, input) {
  return new Promise((resolve, reject) => {
    const child = spawn(CODEX, args, {
      cwd: WORKSPACE,
      windowsHide: true,
      shell: false,
    });
    let stdout = "";
    let stderr = "";
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      try {
        child.kill("SIGKILL");
      } catch {}
      reject(new Error("等待 Codex 回复超时（超过 " + Math.round(TURN_TIMEOUT_MS / 60000) + " 分钟）"));
    }, TURN_TIMEOUT_MS);

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

function readLastMessage() {
  try {
    const t = fs.readFileSync(LAST_FILE, "utf8").trim();
    if (t) return t;
  } catch {}
  return "";
}

async function chatOnce(message) {
  const state = readState();
  let out;

  if (state.threadId) {
    log("CHAT resume thread", state.threadId);
    out = await runCodex(
      ["exec", "resume", "--json", "--skip-git-repo-check", "-o", LAST_FILE, String(state.threadId), "-"],
      message
    );
  } else {
    log("CHAT new thread");
    out = await runCodex(
      ["exec", "--json", "--skip-git-repo-check", "-s", "read-only", "--color", "never", "-o", LAST_FILE, "-"],
      PERSONA + "\n\n" + message
    );
  }

  if (out.code !== 0) {
    const tail = (out.stderr || "").trim().slice(-1200);
    throw new Error("Codex 调用失败（退出码 " + out.code + "）：" + (tail || "无错误信息"));
  }

  if (!state.threadId) {
    const tid = parseThreadId(out.stdout);
    if (!tid) {
      throw new Error("未能取得会话号，请重试或告诉我");
    }
    writeState({ threadId: tid, createdAt: new Date().toISOString(), cwd: WORKSPACE });
    log("NEW THREAD", tid);
  }

  const reply = readLastMessage();
  if (!reply) {
    throw new Error("Codex 没有返回文字回复，请再说一次或换个问法");
  }
  return reply;
}

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
  });
  res.end(body);
}

const PAGE = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<title>Codex 手机通道</title>
<style>
:root{--bg:#0d1117;--panel:#161b22;--line:#30363d;--text:#e6edf3;--dim:#8b949e;--accent:#2f81f7}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;height:100dvh;display:flex;flex-direction:column}
header{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:var(--panel);border-bottom:1px solid var(--line)}
header h1{font-size:16px;margin:0;font-weight:600}
header button{background:transparent;color:var(--dim);border:1px solid var(--line);border-radius:8px;padding:5px 10px;font-size:12px}
#msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:12px}
.row{display:flex;flex-direction:column}
.row.user{align-items:flex-end}
.bubble{max-width:86%;padding:9px 12px;border-radius:14px;line-height:1.55;white-space:pre-wrap;word-break:break-word;font-size:15px}
.user .bubble{background:#1f6feb;border-bottom-right-radius:4px}
.bot .bubble{background:var(--panel);border:1px solid var(--line);border-bottom-left-radius:4px}
.bot .who{color:var(--dim);font-size:12px;margin:0 2px 4px}
.typing{color:var(--dim);font-size:13px;padding:4px 2px}
.error .bubble{border-color:#f85149;color:#ffa198}
form{display:flex;gap:8px;padding:10px;background:var(--panel);border-top:1px solid var(--line);padding-bottom:calc(10px + env(safe-area-inset-bottom))}
input{flex:1;background:#0d1117;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:11px 13px;font-size:16px}
button[type=submit]{background:var(--accent);color:#fff;border:0;border-radius:10px;padding:0 18px;font-size:15px}
button:disabled,input:disabled{opacity:.55}
</style>
</head>
<body>
<header>
  <h1>Codex 手机通道</h1>
  <button id="newbtn">新话题</button>
</header>
<div id="msgs"></div>
<form id="form">
  <input id="inp" autocomplete="off" placeholder="说点什么…">
  <button type="submit">发送</button>
</form>
<script>
const $=s=>document.querySelector(s);
const msgs=$("#msgs"),form=$("#form"),inp=$("#inp"),newbtn=$("#newbtn");
let token=localStorage.getItem("mchat_token")||new URLSearchParams(location.search).get("t")||"";
if(token)localStorage.setItem("mchat_token",token);
function add(role,text,cls){
  const row=document.createElement("div");
  row.className="row "+(role==="user"?"user":"bot");
  if(role==="bot"){const who=document.createElement("div");who.className="who";who.textContent="Codex";row.appendChild(who);}
  const b=document.createElement("div");
  b.className="bubble";
  b.textContent=text;
  if(cls)b.parentNode&&row.classList.add(cls);
  row.appendChild(b);
  msgs.appendChild(row);
  msgs.scrollTop=msgs.scrollHeight;
  return b;
}
function askToken(){
  const t=prompt("请输入访问口令（在你电脑上的启动信息里有）：");
  if(t){token=t.trim();localStorage.setItem("mchat_token",token);}
  return token;
}
async function api(path,body){
  let tk=token;
  if(!tk)tk=askToken();
  const r=await fetch(path,{method:body?"POST":"GET",headers:{"Content-Type":"application/json","x-mchat-token":tk||""},body:body?JSON.stringify(body):undefined});
  if(r.status===401){token="";localStorage.removeItem("mchat_token");askToken();throw new Error("口令不对，请重新输入");}
  return r.json();
}
let waiting=false;
form.addEventListener("submit",async e=>{
  e.preventDefault();
  const msg=inp.value.trim();
  if(!msg||waiting)return;
  add("user",msg);
  inp.value="";
  waiting=true;inp.disabled=true;form.querySelector("button").disabled=true;
  const tip=add("bot","正在思考…");
  try{
    const data=await api("/api/chat",{message:msg});
    tip.textContent=data.reply||"（无回复）";
    tip.parentNode.className="row bot";
  }catch(err){
    tip.textContent="出错了："+err.message;
    tip.parentNode.classList.add("error");
  }finally{
    waiting=false;inp.disabled=false;form.querySelector("button").disabled=false;inp.focus();
    msgs.scrollTop=msgs.scrollHeight;
  }
});
newbtn.addEventListener("click",async()=>{
  if(!confirm("确定开始一个全新话题吗？旧对话仍保存在电脑上。"))return;
  await api("/api/reset",{});
  msgs.innerHTML="";
  add("bot","新话题已开始，想聊什么？");
});
add("bot","连接成功。这是你的 Codex 手机通道，直接发消息即可。");
</script>
</body>
</html>`;

async function readBody(req) {
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

async function main() {
  ensureDataDir();
  const token = await getToken();

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://" + HOST);

    if (req.method === "GET" && url.pathname === "/") {
      res.writeHead(200, {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
      });
      res.end(PAGE);
      return;
    }

    if (req.method === "GET" && url.pathname === "/api/ping") {
      sendJson(res, 200, { ok: true, busy });
      return;
    }

    const headerToken = req.headers["x-mchat-token"] || "";
    if (!tokensEqual(headerToken, token)) {
      sendJson(res, 401, { error: "unauthorized" });
      return;
    }

    if (req.method === "POST" && url.pathname === "/api/reset") {
      writeState({});
      sendJson(res, 200, { ok: true });
      return;
    }

    if (req.method === "POST" && url.pathname === "/api/chat") {
      if (busy) {
        sendJson(res, 409, { error: "上一条还在处理中，请稍等几秒再发" });
        return;
      }
      let payload;
      try {
        const raw = await readBody(req);
        payload = JSON.parse(raw || "{}");
      } catch (e) {
        sendJson(res, 400, { error: "消息格式不对" });
        return;
      }
      const message = String(payload.message || "").trim();
      if (!message) {
        sendJson(res, 400, { error: "消息不能为空" });
        return;
      }
      if (message.length > 8000) {
        sendJson(res, 400, { error: "消息太长，请精简到 8000 字以内" });
        return;
      }

      busy = true;
      try {
        log("REQUEST from phone:", message.slice(0, 80));
        const reply = await chatOnce(message);
        sendJson(res, 200, { reply });
      } catch (err) {
        log("ERROR:", err.message);
        sendJson(res, 500, { error: err.message });
      } finally {
        busy = false;
      }
      return;
    }

    sendJson(res, 404, { error: "not found" });
  });

  server.requestTimeout = 0;
  server.headersTimeout = 0;
  server.keepAliveTimeout = 60000;

  server.listen(PORT, HOST, () => {
    log("LISTENING on http://" + HOST + ":" + PORT);
    log("TOKEN=" + token);
  });

  const stop = () => {
    if (shutdown) return;
    shutdown = true;
    log("Shutting down...");
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 2000).unref();
  };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
}

main().catch((e) => {
  process.stderr.write("FATAL " + e.stack + "\n");
  process.exit(1);
});
