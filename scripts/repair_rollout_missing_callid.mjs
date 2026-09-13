// 修 rollout 账本里"缺 call_id 的 function_call_output"残项（断电/平台 bug 留下的）。
//
// 背景：客户端把心跳注入写成了一条 `function_call_output`，却漏了必填的 `call_id`
// → 服务端 `invalid_request_error: missing field call_id` → 该线每一轮回放都被整轮拒收。
//
// 做法（**不增删行、不改文件总字节数**）：
//   把那条残项就地改写成一条**同字节长度**的合法 `message`（role=user，内容=原心跳文本），
//   尾部用空格补齐到原长度。因为字节总长不变，SQLite 投影里存的行偏移量不会错位。
//
// 用法：
//   node scripts/repair_rollout_missing_callid.mjs --file <rollout.jsonl>            # 演练，不写盘
//   node scripts/repair_rollout_missing_callid.mjs --file <rollout.jsonl> --apply    # 真改（先备份）

import fs from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const flag = (n) => args.includes(n);
const opt = (n, d = null) => {
  const i = args.indexOf(n);
  return i >= 0 && args[i + 1] ? args[i + 1] : d;
};

const file = opt("--file");
if (!file) {
  console.error("缺 --file <rollout.jsonl>");
  process.exit(2);
}
const apply = flag("--apply");

const buf = fs.readFileSync(file); // 读：FileShare 由 fs 默认共享，读得到即可
const starts = [0];
for (let i = 0; i < buf.length; i++) if (buf[i] === 10) starts.push(i + 1);

// ── 找出残项：response_item / function_call_output / 没有 call_id ──
const poison = [];
for (let li = 0; li < starts.length; li++) {
  const s = starts[li];
  const e = li + 1 < starts.length ? starts[li + 1] - 1 : buf.length;
  if (e <= s) continue;
  const raw = buf.subarray(s, e);
  let obj;
  try {
    obj = JSON.parse(raw.toString("utf8"));
  } catch {
    continue;
  }
  const p = obj && obj.payload;
  if (obj.type === "response_item" && p && p.type === "function_call_output" && !p.call_id) {
    poison.push({ line: li + 1, start: s, len: e - s, obj });
  }
}

if (poison.length === 0) {
  console.log("✓ 没有发现缺 call_id 的残项，无需处理。");
  process.exit(0);
}

// ── 生成同长度替身 ────────────────────────────────────────────────
const plan = [];
for (const it of poison) {
  const p = it.obj.payload;
  const text = typeof p.output === "string" ? p.output : JSON.stringify(p.output);
  const neu = {
    timestamp: it.obj.timestamp,
    ordinal: it.obj.ordinal,
    type: "response_item",
    payload: {
      type: "message",
      id: "msg_" + String(p.id || "repaired").replace(/^fco_/, ""),
      role: "user",
      content: [{ type: "input_text", text }],
    },
  };
  if (p.internal_chat_message_metadata_passthrough) {
    neu.payload.internal_chat_message_metadata_passthrough = p.internal_chat_message_metadata_passthrough;
  }
  let bytes = Buffer.from(JSON.stringify(neu), "utf8");
  if (bytes.length > it.len) {
    console.error(`✗ 第 ${it.line} 行：替身(${bytes.length}B) 比原文(${it.len}B) 长，拒绝执行（不写盘）`);
    process.exit(3);
  }
  const pad = it.len - bytes.length;
  if (pad > 0) bytes = Buffer.concat([bytes, Buffer.alloc(pad, 0x20)]);
  // 自检：长度必须严丝合缝，且必须能解析
  if (bytes.length !== it.len) {
    console.error(`✗ 第 ${it.line} 行：长度不匹配，拒绝执行（不写盘）`);
    process.exit(3);
  }
  JSON.parse(bytes.toString("utf8"));
  plan.push({ ...it, bytes, pad });
}

console.log(`== 修复计划 ==`);
console.log(`  文件：${path.resolve(file)}`);
console.log(`  总字节：${buf.length}  总行数：${starts.length}  残项：${plan.length} 条`);
for (const r of plan) {
  console.log(`  第 ${r.line} 行  原 ${r.len}B → 新 ${r.bytes.length}B（空格补齐 ${r.pad}B）  ${r.obj.timestamp}`);
}
console.log(`  替身形态：response_item / message / role=user / 内容=原心跳文本`);

if (!apply) {
  console.log("\n（演练结束；要真改加 --apply，会先备份）");
  process.exit(0);
}

// ── 备份（回滚点）──
const stamp = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);
const bak = `${file}.bak-plt003-${stamp}`;
fs.copyFileSync(file, bak);
console.log(`\n备份：${bak}`);

// ── 就地写（偏移量写死，字节数不变 → 后面所有行位置不动）──
const fd = fs.openSync(file, "r+");
try {
  for (const r of plan) {
    fs.writeSync(fd, r.bytes, 0, r.bytes.length, r.start);
  }
  fs.fsyncSync(fd);
} finally {
  fs.closeSync(fd);
}

// ── 写后核验 ──
const after = fs.readFileSync(file);
const aStarts = [0];
for (let i = 0; i < after.length; i++) if (after[i] === 10) aStarts.push(i + 1);
const problems = [];
if (after.length !== buf.length) problems.push(`总字节变了：${buf.length} → ${after.length}`);
if (aStarts.length !== starts.length) problems.push(`行数变了：${starts.length} → ${aStarts.length}`);
for (const r of plan) {
  const s = aStarts[r.line - 1];
  const e = r.line < aStarts.length ? aStarts[r.line] - 1 : after.length;
  try {
    const o = JSON.parse(after.subarray(s, e).toString("utf8"));
    if (o.type !== "response_item" || o.payload.type !== "message") problems.push(`第 ${r.line} 行改写结果不对`);
  } catch (err) {
    problems.push(`第 ${r.line} 行改写后不是合法 JSON：${err.message}`);
  }
}
// 全文逐行 JSON 自检（残项没了才算过）
let bad = 0;
for (let li = 0; li < aStarts.length; li++) {
  const s = aStarts[li];
  const e = li + 1 < aStarts.length ? aStarts[li + 1] - 1 : after.length;
  if (e <= s) continue;
  try {
    JSON.parse(after.subarray(s, e).toString("utf8"));
  } catch {
    bad++;
  }
}
if (bad) problems.push(`全文有 ${bad} 行解析失败`);

const leftovers = [];
for (let li = 0; li < aStarts.length; li++) {
  const s = aStarts[li];
  const e = li + 1 < aStarts.length ? aStarts[li + 1] - 1 : after.length;
  if (e <= s) continue;
  try {
    const o = JSON.parse(after.subarray(s, e).toString("utf8"));
    if (o.type === "response_item" && o.payload?.type === "function_call_output" && !o.payload.call_id) {
      leftovers.push(li + 1);
    }
  } catch {}
}
if (leftovers.length) problems.push(`仍有残项：${leftovers.join(", ")}`);

if (problems.length) {
  console.error("\n✗ 写后核验不过：\n  - " + problems.join("\n  - "));
  console.error(`回滚：Copy-Item '${bak}' '${file}' -Force`);
  process.exit(4);
}
console.log(`\n✓ 已修复 ${plan.length} 条；总字节 ${after.length}（不变）、行数 ${aStarts.length}（不变）、全文 JSON 全部可解析、无残留残项。`);
console.log(`回滚：Copy-Item '${bak}' '${file}' -Force`);
