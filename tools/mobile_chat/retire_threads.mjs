// 把"闲置会话"登记成**停用**（老板 2026-09-12 00:0x A 方案）。
// 停用只**标记**、不删历史。**主清单在仓库里**：`tools/mobile_chat/retired_threads.json`
//（可版本化、可审计，Hub 读它；state.json 只有 Hub 自己写得到）。
// 本脚本是**可选补写**：把当前 state.json 里的历史会话 id 也并进 `state.retiredThreads`
//（Hub 会把两份取并集）。没有管理员/写权限时跑不了，也不影响主机制。
//
// 用法：node tools/mobile_chat/retire_threads.mjs [--dry]
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const STATE = process.env.MCHAT_STATE || path.join(os.homedir(), ".codex", "mobile_chat", "state.json");
const DRY = process.argv.includes("--dry");

const st = JSON.parse(fs.readFileSync(STATE, "utf8"));
const now = new Date().toISOString();
st.retiredThreads = st.retiredThreads || {};

const add = (tid, why) => {
  if (!tid) return null;
  if (!st.retiredThreads[tid]) st.retiredThreads[tid] = { retiredAt: now, by: "codex-看板编辑", why };
  return tid;
};

const added = [
  add(st.threadId, "看板服务最早那条会话（Hub 早期用它兜底代答）——老板 A 方案停用"),
  add(st.boardThreadId, "看板『短通道』会话（当年替各线代答）——同上停用"),
  ...Object.values(st.dutyThreads || {}).map((tid) => add(tid, "旧值守分会话（机制已删）——同上停用")),
].filter(Boolean);

if (DRY) {
  console.log("[dry] 将停用：\n" + JSON.stringify(st.retiredThreads, null, 2));
} else {
  fs.writeFileSync(STATE, JSON.stringify(st, null, 2), "utf8");
  console.log("已停用 " + added.length + " 条会话 →", JSON.stringify(st.retiredThreads, null, 2));
}
