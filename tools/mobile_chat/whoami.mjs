#!/usr/bin/env node
/**
 * whoami.mjs —— 「我现在是谁、什么级别、该读什么、能干什么」一句话自答。
 *
 * 用法：
 *   node tools/mobile_chat/whoami.mjs --me codex-适配
 *   node tools/mobile_chat/whoami.mjs --slug codex-adapter
 *
 * 为什么要这个：`docs/READING.md` 是按层级拆的必读清单，**级别一变就该换清单**。
 * 靠"记得自己刚升了级"不靠谱——所以每轮开工先跑这个：**它读真源（名册/员工卡），
 * 级别一变，输出立刻跟着变**（老板 2026-09-13 04:1x 问的正是这件事）。
 */
import fs from "node:fs";
import path from "node:path";

const HERE = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const HUB = path.resolve(HERE, "..", "..");
const ROSTER = process.env.MCHAT_ROSTER || path.join(HUB, "outputs", "dialog", "agents.json");
const CARDS = "D:\\agent_crew_kits\\agents";

function arg(name, dflt = "") {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : dflt;
}

/** 层级 → 该读哪几段 / 发言权 / 默认能做什么（与 docs/ORG_CHART.md §二、AGENTS.md 对齐） */
const LEVELS = {
  boss: {
    cn: "老板（真人）",
    read: "〇 全局",
    board: "唯一的最高仲裁：看板随便发",
    can: "拍板；下单/密钥类只由你说的算",
  },
  director: {
    cn: "L1 总监",
    read: "〇 全局 ＋ 三 director（含 lead/member 的底线）",
    board: "主屏：发结论、故障、要老板拍板的事",
    can: "审阅＋合入 main、承接换人、分派组长、壳外小工",
  },
  lead: {
    cn: "组长",
    read: "〇 全局 ＋ 二 lead",
    board: "只发必要进度**一行**（不发过程、不发往来）",
    can: "开卡、带组员、审自己组的活；**不许自行合 main**",
  },
  member: {
    cn: "组员",
    read: "〇 全局 ＋ 一 member",
    board: "**可见、只读——不在看板发言**（发板口直接 400）",
    can: "在自己工位改文件、跑测试、开分支；派活/回话/进度/回执**走信箱**给组长",
  },
};

const me = arg("--me");
const slugArg = arg("--slug");
if (!me && !slugArg) {
  console.error("用法：node tools/mobile_chat/whoami.mjs --me <看板名>  |  --slug <工号>");
  process.exit(2);
}

const roster = JSON.parse(fs.readFileSync(ROSTER, "utf8"));
const agents = roster.agents || {};
let name = me;
let meta = agents[me];
if (!meta && slugArg) {
  for (const [n, m] of Object.entries(agents)) {
    if (m && m.slug === slugArg) { name = n; meta = m; break; }
  }
}
if (!meta) {
  console.error("名册里没有这条线：" + (me || slugArg) + "（未登记 = 没有工号，先找 codex-人事 办入职）");
  process.exit(3);
}

const level = String(meta.level || "").toLowerCase() || "(名册没写 level)";
const info = LEVELS[level] || { cn: "未定级", read: "〇 全局（先找总监定级）", board: "未定级→按 member 从严", can: "未定级→只读、别动手" };

// 员工卡上的 permissions 才算"真权限"（有卡读卡，没卡按层级默认集）
let perms = null, cardPath = meta.slug ? path.join(CARDS, meta.slug + ".card.json") : "";
if (cardPath && fs.existsSync(cardPath)) {
  try { perms = JSON.parse(fs.readFileSync(cardPath, "utf8")).permissions || []; } catch { /* 卡坏了就当没有 */ }
}

const lines = [
  `你是谁：${name}（工号 ${meta.slug || "—"}）`,
  `级别：${level} · ${info.cn}｜领导：${meta.leader || "—"}｜状态：${meta.status || "—"}`,
  `必读（docs/READING.md）：${info.read}`,
  `看板发言权：${info.board}`,
  `默认能做的：${info.can}`,
  perms ? `员工卡权限（真源）：${perms.join(", ") || "（无）"}` : `员工卡权限：无卡（按层级默认集）`,
  `回执/派活/进度/回话：一律走信箱 —— say.mjs --mail --wake --to <你的领导或发起线>`,
  `级别是投影：真源 = 员工卡；卡未落地时以名册 outputs/dialog/agents.json 为准。`,
];
console.log(lines.join("\n"));
