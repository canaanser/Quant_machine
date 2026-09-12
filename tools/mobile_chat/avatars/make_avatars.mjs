// HUB-AVATAR 头像素材生成器（codex-看板编辑）
//
// 为什么用代码生成、不用 AI 生图：
//   ① 本机**没有**内置生图工具；走 CLI 兜底要 OPENAI_API_KEY（平台面，得老板点头）——
//      而这件不该为了一张头像卡住全队；
//   ② 头像要**离线、确定性、可复现**（团队资产不该依赖外部服务）；
//   ③ 渲染的取图契约本身就收 `.svg`（且带 `CSP default-src 'none'` 禁脚本），
//      扁平矢量脸在手机页上就是"卡通人物头像"要的效果。
//
// 契约（照 codex-渲染 的 `avatars/README.md`）：文件名 = **工号(slug)**；
//   性别取自名册 `outputs/dialog/agents.json` 的 `gender`；**缺 gender 不编**（跳过，页面退回首字圆点）。
//
// 用法：node tools/mobile_chat/avatars/make_avatars.mjs [--dry]
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..", "..");
const AGENTS = path.join(ROOT, "outputs", "dialog", "agents.json");
const DRY = process.argv.includes("--dry");

// 确定性：同一个工号永远得到同一张脸（hue / 发型 / 肤色都由 slug 哈希决定）
function seed(str) {
  return crypto.createHash("sha1").update(String(str)).digest();
}
const pick = (buf, i, arr) => arr[buf[i % buf.length] % arr.length];

const SKIN = ["#f2c9a0", "#e8b48b", "#d9a173", "#c98a5e", "#a9714b", "#f7d7bb"];
const HAIR = ["#2f2a26", "#4a3728", "#6b4a2f", "#8a6a3f", "#1f1c1a", "#3b3f4a", "#7a4b3a"];
const CLOTH = ["#4f6fa8", "#3f8f7a", "#a05a6a", "#6b5aa6", "#b07a3a", "#4a7f8f", "#8f5a4a", "#5a6b8f"];
const BG = ["#dfe8f5", "#e6f0e6", "#f5e8df", "#ece4f5", "#e4f0f2", "#f5eee0", "#eae6f7", "#f2e6ec"];

// 女：三种发型；男：三种发型。都用"头 + 发 + 眼 + 笑 + 肩"这套最小笔画，保证一眼是人脸。
function hairSvg(sex, s, hair) {
  if (sex === "女") {
    const v = s[7] % 3;
    if (v === 0) {
      // 长发披肩
      return `<path d="M74 118c0-38 24-58 54-58s54 20 54 58v46c0 8-6 12-12 12h-6v-52c0-22-14-34-36-34s-36 12-36 34v52h-6c-6 0-12-4-12-12z" fill="${hair}"/>`;
    }
    if (v === 1) {
      // 中长发 + 刘海
      return `<path d="M78 116c0-34 22-54 50-54s50 20 50 54v10c0 6-4 10-10 10h-4v-25c-8 5-20 8-36 8s-28-3-36-8v25h-4c-6 0-10-4-10-10z" fill="${hair}"/>`;
    }
    // 丸子头
    return `<circle cx="128" cy="60" r="16" fill="${hair}"/><path d="M80 118c0-34 22-54 48-54s48 20 48 54c0 6-4 10-10 10h-4v-26c-8 5-20 8-34 8s-26-3-34-8v26h-4c-6 0-10-4-10-10z" fill="${hair}"/>`;
  }
  const v = s[7] % 3;
  if (v === 0) {
    // 短寸
    return `<path d="M80 112c0-30 20-50 48-50s48 20 48 50c0 4-2 6-6 6h-6v-16c-10 4-22 6-36 6s-26-2-36-6v16h-6c-4 0-6-2-6-6z" fill="${hair}"/>`;
  }
  if (v === 1) {
    // 侧分
    return `<path d="M78 114c0-32 20-52 50-52 26 0 44 16 46 40-12-6-26-10-42-8-16 2-30 8-44 18-6 4-10 4-10 2z" fill="${hair}"/>`;
  }
  // 卷短发
  return `<path d="M78 116c0-32 22-54 50-54s50 22 50 54c0 4-2 6-6 6h-4v-14c-12 6-26 9-40 9s-28-3-40-9v14h-4c-4 0-6-2-6-6z" fill="${hair}"/><circle cx="86" cy="88" r="10" fill="${hair}"/><circle cx="170" cy="88" r="10" fill="${hair}"/>`;
}

function avatarSvg(slug, sex) {
  const s = seed(slug + "|" + sex);
  const skin = pick(s, 1, SKIN);
  const hair = pick(s, 2, HAIR);
  const cloth = pick(s, 3, CLOTH);
  const bg = pick(s, 4, BG);
  const hw = sex === "女" ? 38 : 46; // 男性肩更宽（一眼能分）
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256" role="img" aria-label="${slug}">
  <circle cx="128" cy="128" r="128" fill="${bg}"/>
  <ellipse cx="128" cy="240" rx="${hw}" ry="72" fill="${cloth}"/>
  <rect x="118" y="146" width="20" height="22" rx="9" fill="${skin}"/>
  <ellipse cx="128" cy="118" rx="46" ry="50" fill="${skin}"/>
  ${hairSvg(sex, s, hair)}
  <ellipse cx="112" cy="118" rx="5" ry="6.5" fill="#2b2b2b"/>
  <ellipse cx="144" cy="118" rx="5" ry="6.5" fill="#2b2b2b"/>
  <path d="M113 141q15 12 30 0" stroke="#8a5a4a" stroke-width="4.5" fill="none" stroke-linecap="round"/>
  <path d="M103 104q9-5 18-2" stroke="${hair}" stroke-width="3.5" fill="none" stroke-linecap="round"/>
  <path d="M135 102q9-3 18 2" stroke="${hair}" stroke-width="3.5" fill="none" stroke-linecap="round"/>
</svg>
`;
}

const cfg = JSON.parse(fs.readFileSync(AGENTS, "utf8"));
const agents = cfg.agents || {};
let made = 0;
let skipped = [];
for (const [name, meta] of Object.entries(agents)) {
  const slug = String((meta && meta.slug) || "").trim();
  const sex = String((meta && meta.gender) || "").trim();
  if (!slug) {
    skipped.push(name + "(无工号)");
    continue;
  }
  if (sex !== "男" && sex !== "女") {
    skipped.push(name + "(无性别)"); // 缺性别**不编**：跳过，页面退回首字圆点
    continue;
  }
  if (/·退役$/.test(name)) {
    skipped.push(name + "(退役)");
    continue;
  }
  const file = path.join(HERE, slug + ".svg");
  if (!DRY) fs.writeFileSync(file, avatarSvg(slug, sex), "utf8");
  made++;
}
process.stdout.write("生成 " + made + " 张" + (DRY ? "（dry，未落盘）" : "") + "；跳过：" + (skipped.join("、") || "无") + "\n");
