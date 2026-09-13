// 把 shared/ 同步进每个云函数目录（微信云函数各自打包，不能引用函数目录之外的文件）。
// 用途：上传前跑一次 `npm run sync`。真源永远只有 shared/ 一份，这里是**生成物**。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SHARED = path.join(ROOT, "shared");
const COMMON = path.join(ROOT, "cloudfn-common");
const FN_ROOT = path.join(ROOT, "cloudfunctions");

const sharedFiles = fs.readdirSync(SHARED).filter((f) => f.endsWith(".js"));
const commonFiles = fs.readdirSync(COMMON).filter((f) => f.endsWith(".js"));
const fns = fs.readdirSync(FN_ROOT, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name);

let n = 0;
for (const fn of fns) {
  const fd = path.join(FN_ROOT, fn);
  const dest = path.join(fd, "_shared");
  fs.mkdirSync(dest, { recursive: true });
  for (const f of sharedFiles) { fs.copyFileSync(path.join(SHARED, f), path.join(dest, f)); n++; }
  for (const f of commonFiles) { fs.copyFileSync(path.join(COMMON, f), path.join(fd, f)); n++; }   // 适配层也各函数一份
  // 每函数一份 package.json：声明 ESM + 依赖（部署时用 --remote-npm-install 在云端装依赖）
  const pj = path.join(fd, "package.json");
  const manifest = {
    name: fn,
    version: "1.0.0",
    type: "module",
    main: "index.js",
    dependencies: { "wx-server-sdk": "~2.6.3" },
  };
  fs.writeFileSync(pj, JSON.stringify(manifest, null, 2) + "\n", "utf8"); n++;
}
console.log(`synced ${sharedFiles.length} shared + ${commonFiles.length} common -> ${fns.length} cloudfunctions (${n} copies)`);
