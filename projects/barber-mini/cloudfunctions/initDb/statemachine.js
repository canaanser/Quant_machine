// 订单状态机 —— **唯一真源**（云函数 require 它；客户端不引，避免打包越界）。
// ⚠️ 2026-09-14：改回 CommonJS —— 微信云函数运行时**不认 ESM**（实测 145 code exit unexpected）。
const STATES = ["pending", "reserved", "queuing", "serving", "completed", "cancelled"];

const TRANSITIONS = {
  pending: ["reserved", "queuing", "cancelled"],   // 现场排队：pending → queuing（跳过 reserved）
  reserved: ["queuing", "cancelled"],
  queuing: ["serving", "cancelled"],
  serving: ["completed", "cancelled"],
  completed: [],
  cancelled: [],
};

function canTransition(from, to) { return (TRANSITIONS[from] || []).includes(to); }

function assertTransition(from, to) {
  if (!canTransition(from, to)) throw new Error("非法状态迁移：" + from + " → " + to);
  return true;
}

const isTerminal = (state) => state === "completed" || state === "cancelled";

module.exports = { STATES, canTransition, assertTransition, isTerminal };
