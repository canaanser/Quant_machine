// 本地预览服务（零依赖）：node scripts/preview.mjs → 浏览器打开打印出来的地址
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PORT = Number(process.env.PREVIEW_PORT || 8787);
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8" };

http.createServer((req, res) => {
  const url = decodeURIComponent((req.url || "/").split("?")[0]);
  let file = path.join(ROOT, url === "/" ? "preview/index.html" : url);
  if (!file.startsWith(ROOT)) { res.writeHead(403).end("forbidden"); return; }   // 防目录穿越
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404).end("not found: " + url); return; }
  res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
}).listen(PORT, () => {
  console.log("预览已启动 → 浏览器打开： http://localhost:" + PORT + "/");
  console.log("（数据是本地 mock，逻辑用的是 shared/ 真实代码；Ctrl+C 停止）");
});
