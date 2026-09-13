// 判别性单测：这些用例就是契约的"门"——改坏了必须红。
import test from "node:test";
import assert from "node:assert/strict";
import { canTransition, assertTransition, isTerminal } from "../shared/statemachine.js";
import { compareOrders, sortQueue, normalizePriority, PRIORITY } from "../shared/priority.js";
import { overlaps, hasConflict, findFreeSlot, endOf } from "../shared/slots.js";

const HOUR = 3600 * 1000;
const T0 = 1789260000000; // 固定基准时刻，避免依赖当前时间

test("状态机：主链合法", () => {
  const chain = ["pending", "reserved", "queuing", "serving", "completed"];
  for (let i = 0; i < chain.length - 1; i++) {
    assert.equal(canTransition(chain[i], chain[i + 1]), true, chain[i] + "→" + chain[i + 1]);
  }
});

test("状态机：现场单可 pending→queuing，但**不许跳级到 serving/completed**", () => {
  assert.equal(canTransition("pending", "queuing"), true);
  assert.equal(canTransition("pending", "serving"), false);
  assert.equal(canTransition("pending", "completed"), false);
  assert.equal(canTransition("queuing", "completed"), false);   // 必须先 serving
  assert.throws(() => assertTransition("pending", "completed"), /非法状态迁移/);
});

test("状态机：终态不可再变", () => {
  for (const to of ["queuing", "serving", "completed", "cancelled", "pending"]) {
    assert.equal(canTransition("completed", to), false);
    assert.equal(canTransition("cancelled", to), false);
  }
  assert.equal(isTerminal("completed"), true);
  assert.equal(isTerminal("serving"), false);
});

test("优先级：真源是 priority 字段，缺省按 isPrepaid/预约推导", () => {
  assert.equal(normalizePriority({ priority: 0 }), PRIORITY.PREPAID);
  assert.equal(normalizePriority({ isPrepaid: true }), PRIORITY.PREPAID);
  assert.equal(normalizePriority({ appointmentTime: T0 }), PRIORITY.RESERVED);
  assert.equal(normalizePriority({ appointmentTime: 0 }), PRIORITY.WALKIN);
});

test("排序：**预付款只在同一时段内优先，不跨段抢**", () => {
  // 同时段：预付款（后预约）应排在已预约（先预约）之前
  const sameSlot = [
    { _id: "a", isPrepaid: false, appointmentTime: T0 + 5 * 60 * 1000, createdAt: 1 },
    { _id: "b", isPrepaid: true, appointmentTime: T0, createdAt: 2 },
  ];
  assert.equal(sortQueue(sameSlot)[0]._id, "b");

  // 跨时段：预付款**不许**插到更早的时段前面
  const crossSlot = [
    { _id: "early", isPrepaid: false, appointmentTime: T0, createdAt: 5 },
    { _id: "late-prepaid", isPrepaid: true, appointmentTime: T0 + 2 * HOUR, createdAt: 1 },
  ];
  assert.equal(sortQueue(crossSlot)[0]._id, "early");
  assert.ok(compareOrders(crossSlot[0], crossSlot[1]) < 0);
});

test("排序：同时段同优先级 → 先到先得；现场单排在同时段预付款之后", () => {
  const list = [
    { _id: "walkin", appointmentTime: 0, createdAt: 1 },
    { _id: "reserved2", appointmentTime: T0, createdAt: 9 },
    { _id: "reserved1", appointmentTime: T0, createdAt: 3 },
  ];
  const out = sortQueue(list).map((o) => o._id);
  assert.deepEqual(out, ["reserved1", "reserved2", "walkin"]);
});

test("槽位：重叠判定与冲突检测（completed/cancelled 不占坑）", () => {
  assert.equal(overlaps(T0, 40 * 60 * 1000, T0 + 20 * 60 * 1000, 40 * 60 * 1000), true);
  assert.equal(overlaps(T0, 40 * 60 * 1000, T0 + 40 * 60 * 1000, 40 * 60 * 1000), false); // 首尾相接不算冲突
  const orders = [
    { status: "reserved", appointmentTime: T0, duration: 40 * 60 * 1000 },
    { status: "completed", appointmentTime: T0 - HOUR, duration: 40 * 60 * 1000 },
  ];
  assert.equal(hasConflict(T0 + 10 * 60 * 1000, 30 * 60 * 1000, orders), true);
  assert.equal(hasConflict(T0 - HOUR, 40 * 60 * 1000, orders), false);  // 已完成的单不占坑
});

test("槽位：findFreeSlot 从冲突时刻往后找到空位，且返回的是可插入时刻", () => {
  const dur = 40 * 60 * 1000;
  const orders = [{ status: "serving", appointmentTime: T0, duration: dur }];
  const got = findFreeSlot(T0, dur, orders);
  assert.equal(got, T0 + 40 * 60 * 1000);
  assert.equal(hasConflict(got, dur, orders), false);
  assert.equal(endOf(got, dur) - got, dur);
  // 排满时返回 null（找不到就老实说找不到，别硬塞）
  const full = [{ status: "queuing", appointmentTime: T0, duration: 12 * HOUR }];
  assert.equal(findFreeSlot(T0, dur, full, { maxSteps: 3 }), null);
});
