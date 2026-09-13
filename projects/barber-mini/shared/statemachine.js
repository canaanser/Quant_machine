// 订单状态机 —— **唯一真源**：云函数与小程序都必须 import 这份，不许各写一版。
// 契约见 docs/reports/PLT-009_barber_kickoff.md §二。
export const STATES = ["pending", "reserved", "queuing", "serving", "completed", "cancelled"];

const TRANSITIONS = {
  pending: ["reserved", "queuing", "cancelled"],   // 现场排队：pending → queuing（跳过 reserved）
  reserved: ["queuing", "cancelled"],
  queuing: ["serving", "cancelled"],
  serving: ["completed", "cancelled"],
  completed: [],
  cancelled: [],
};

export function canTransition(from, to) {
  return (TRANSITIONS[from] || []).includes(to);
}

/** 非法迁移**必须抛错**（云函数据此拒绝并留痕），不许静默改状态。 */
export function assertTransition(from, to) {
  if (!canTransition(from, to)) {
    throw new Error("非法状态迁移：" + from + " → " + to);
  }
  return true;
}

export function isTerminal(state) {
  return state === "completed" || state === "cancelled";
}
