// 判别性单测（CommonJS）：状态机 / 优先级 / 槽位
const test = require("node:test");
const assert = require("node:assert/strict");
const sm = require("../shared/statemachine.js");
const pr = require("../shared/priority.js");
const sl = require("../shared/slots.js");

const HOUR = 3600 * 1000, T0 = 1789260000000;

test("状态机：主链合法；现场单可 pending→queuing", () => {
  const chain = ["pending", "reserved", "queuing", "serving", "completed"];
  for (let i = 0; i < chain.length - 1; i++) assert.equal(sm.canTransition(chain[i], chain[i + 1]), true);
  assert.equal(sm.canTransition("pending", "queuing"), true);
});

test("状态机：**不许跳级**；终态不可再变", () => {
  assert.equal(sm.canTransition("pending", "serving"), false);
  assert.equal(sm.canTransition("pending", "completed"), false);
  assert.equal(sm.canTransition("queuing", "completed"), false);
  assert.throws(() => sm.assertTransition("pending", "completed"), /非法状态迁移/);
  for (const to of ["queuing", "serving", "completed", "pending"]) assert.equal(sm.canTransition("completed", to), false);
  assert.equal(sm.isTerminal("cancelled"), true);
  assert.equal(sm.isTerminal("serving"), false);
});

test("优先级：真源是 priority，缺省按 isPrepaid / 有无预约推", () => {
  assert.equal(pr.normalizePriority({ priority: 0 }), pr.PRIORITY.PREPAID);
  assert.equal(pr.normalizePriority({ isPrepaid: true }), pr.PRIORITY.PREPAID);
  assert.equal(pr.normalizePriority({ appointmentTime: T0 }), pr.PRIORITY.RESERVED);
  assert.equal(pr.normalizePriority({ appointmentTime: 0 }), pr.PRIORITY.WALKIN);
});

test("排序：预付款**同段优先、跨段不抢**；同段同优先级先到先得", () => {
  const same = [
    { _id: "a", isPrepaid: false, appointmentTime: T0 + 5 * 60 * 1000, createdAt: 1 },
    { _id: "b", isPrepaid: true, appointmentTime: T0, createdAt: 2 },
  ];
  assert.equal(pr.sortQueue(same, T0)[0]._id, "b");
  const cross = [
    { _id: "early", isPrepaid: false, appointmentTime: T0, createdAt: 5 },
    { _id: "latePrepaid", isPrepaid: true, appointmentTime: T0 + 2 * HOUR, createdAt: 1 },
  ];
  assert.equal(pr.sortQueue(cross, T0)[0]._id, "early");
  const tie = [
    { _id: "w", appointmentTime: 0, createdAt: 1 },
    { _id: "r2", appointmentTime: T0, createdAt: 9 },
    { _id: "r1", appointmentTime: T0, createdAt: 3 },
  ];
  // 现场单算"当前时段"：T0 桶内 r1/r2 是预约(1) 优先于现场(2)；同优先级按 createdAt
  assert.deepEqual(pr.sortQueue(tie, T0).map((o) => o._id), ["r1", "r2", "w"]);
});

test("槽位：重叠判定、冲突检测（completed/cancelled 不占坑）、findFreeSlot", () => {
  assert.equal(sl.overlaps(T0, 40 * 60 * 1000, T0 + 20 * 60 * 1000, 40 * 60 * 1000), true);
  assert.equal(sl.overlaps(T0, 40 * 60 * 1000, T0 + 40 * 60 * 1000, 40 * 60 * 1000), false);
  const orders = [
    { status: "reserved", appointmentTime: T0, duration: 40 * 60 * 1000 },
    { status: "completed", appointmentTime: T0 - HOUR, duration: 40 * 60 * 1000 },
  ];
  assert.equal(sl.hasConflict(T0 + 10 * 60 * 1000, 30 * 60 * 1000, orders), true);
  assert.equal(sl.hasConflict(T0 - HOUR, 40 * 60 * 1000, orders), false);
  const dur = 40 * 60 * 1000;
  const busy = [{ status: "serving", appointmentTime: T0, duration: dur }];
  assert.equal(sl.findFreeSlot(T0, dur, busy), T0 + dur);
  assert.equal(sl.hasConflict(sl.findFreeSlot(T0, dur, busy), dur, busy), false);
  assert.equal(sl.findFreeSlot(T0, dur, [{ status: "queuing", appointmentTime: T0, duration: 12 * HOUR }], { maxSteps: 3 }), null);
});
