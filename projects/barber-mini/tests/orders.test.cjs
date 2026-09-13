// 业务逻辑判别性单测（CommonJS，跑在内存 store 上，不需要云环境）
const test = require("node:test");
const assert = require("node:assert/strict");
const { makeStore } = require("./mockstore.cjs");
const od = require("../shared/orders.js");

const HOUR = 3600 * 1000, MIN = 60 * 1000, T0 = 1789260000000;
let clk = T0; const clock = () => clk;

function setup() {
  clk = T0;
  return makeStore({
    barbers: [{ _id: "b1", name: "阿明", status: "idle", currentOrderId: null }],
    serviceItems: [
      { _id: "s1", barberId: "b1", name: "剪发", defaultDuration: 40 * MIN, price: 38 },
      { _id: "s2", barberId: "b1", name: "烫发", defaultDuration: 150 * MIN, price: 288 },
    ],
    orders: [],
  });
}

test("主链A：预约 → 排队 → 开始 → 完成（理发师状态跟着走）", async () => {
  const st = setup();
  const r = await od.createOrder(st, { barberId: "b1", serviceItemId: "s1", customerOpenid: "c1", customerName: "小王", customerType: "woman", appointmentTime: T0 + HOUR }, clock);
  assert.equal(r.created, true);
  assert.equal(r.order.status, "reserved");
  assert.equal(r.order.priority, 1);
  await od.transitionOrder(st, { orderId: r.order._id, to: "queuing" }, clock);
  clk += MIN;
  const serving = await od.transitionOrder(st, { orderId: r.order._id, to: "serving" }, clock);
  assert.equal(serving.order.actualStartTime, clk);
  assert.equal((await st.getBarber("b1")).status, "busy");
  clk += 30 * MIN;
  await od.transitionOrder(st, { orderId: r.order._id, to: "completed" }, clock);
  assert.equal((await st.getBarber("b1")).status, "idle");
  assert.equal((await st.getBarber("b1")).currentOrderId, null);
});

test("主链B：现场排队（pending→queuing）→ 服务 → 完成；priority=2", async () => {
  const st = setup();
  const r = await od.createOrder(st, { barberId: "b1", serviceItemId: "s1", customerOpenid: "c2", customerType: "man" }, clock);
  assert.equal(r.order.status, "queuing");
  assert.equal(r.order.priority, 2);
  await od.transitionOrder(st, { orderId: r.order._id, to: "serving" }, clock);
  clk += 40 * MIN;
  assert.equal((await od.transitionOrder(st, { orderId: r.order._id, to: "completed" }, clock)).order.status, "completed");
});

test("幂等：同请求重放不产生第二单；重复同向迁移不重复计时", async () => {
  const st = setup();
  const p = { barberId: "b1", serviceItemId: "s1", customerOpenid: "c9", appointmentTime: T0 + HOUR };
  const a = await od.createOrder(st, p, clock);
  const b = await od.createOrder(st, p, clock);
  assert.equal(a.created, true);
  assert.equal(b.created, false);
  assert.equal(a.order._id, b.order._id);
  assert.equal((await st.listOrders("b1")).length, 1);
  assert.equal((await od.transitionOrder(st, { orderId: a.order._id, to: "queuing" }, clock)).changed, true);
  assert.equal((await od.transitionOrder(st, { orderId: a.order._id, to: "queuing" }, clock)).changed, false);
});

test("非法迁移被拒（reserved→completed）；终态不可再改", async () => {
  const st = setup();
  const r = await od.createOrder(st, { barberId: "b1", serviceItemId: "s1", customerOpenid: "c3", appointmentTime: T0 + HOUR }, clock);
  await assert.rejects(() => od.transitionOrder(st, { orderId: r.order._id, to: "completed" }, clock), /非法状态迁移/);
  await od.transitionOrder(st, { orderId: r.order._id, to: "queuing" }, clock);
  await od.transitionOrder(st, { orderId: r.order._id, to: "serving" }, clock);
  await od.transitionOrder(st, { orderId: r.order._id, to: "completed" }, clock);
  await assert.rejects(() => od.transitionOrder(st, { orderId: r.order._id, to: "serving" }, clock), /终态/);
});

test("冲突：同时段重复预约被拒；首尾相接不算冲突", async () => {
  const st = setup();
  const dur = 40 * MIN;
  await od.createOrder(st, { barberId: "b1", serviceItemId: "s1", customerOpenid: "c1", appointmentTime: T0 + HOUR }, clock);
  await assert.rejects(() => od.createOrder(st, { barberId: "b1", serviceItemId: "s1", customerOpenid: "c2", appointmentTime: T0 + HOUR + 10 * MIN }, clock), /已被占用/);
  assert.equal((await od.createOrder(st, { barberId: "b1", serviceItemId: "s1", customerOpenid: "c3", appointmentTime: T0 + HOUR + dur }, clock)).created, true);
});

test("乐观锁：拿旧 updatedAt 提交被拒", async () => {
  const st = setup();
  const r = await od.createOrder(st, { barberId: "b1", serviceItemId: "s1", customerOpenid: "c4", appointmentTime: T0 + HOUR }, clock);
  const stale = r.order.updatedAt;
  clk += 1000;
  await od.transitionOrder(st, { orderId: r.order._id, to: "queuing" }, clock);
  await assert.rejects(() => od.transitionOrder(st, { orderId: r.order._id, to: "cancelled", expectedUpdatedAt: stale }, clock), /乐观锁/);
});

test("排队序：现场单算当前时段；同段预付款优先；未来时段不许插到现场前面", async () => {
  const st = setup();
  const b = { barberId: "b1", serviceItemId: "s1" };
  await od.createOrder(st, Object.assign({}, b, { customerOpenid: "c1", appointmentTime: T0 + HOUR }), clock);
  await od.createOrder(st, Object.assign({}, b, { customerOpenid: "c3", appointmentTime: T0 + 3 * HOUR, isPrepaid: true }), clock);
  await od.createOrder(st, Object.assign({}, b, { customerOpenid: "c4", isPrepaid: true }), clock);
  await od.createOrder(st, Object.assign({}, b, { customerOpenid: "c5" }), clock);
  const q = await od.queueView(st, "b1", T0);
  assert.deepEqual(q.map((o) => o.customerOpenid), ["c4", "c5", "c1", "c3"]);
});

test("理发师状态：手上有单不许切空闲；完成后可休息", async () => {
  const st = setup();
  const r = await od.createOrder(st, { barberId: "b1", serviceItemId: "s1", customerOpenid: "c5" }, clock);
  await od.transitionOrder(st, { orderId: r.order._id, to: "serving" }, clock);
  await assert.rejects(() => od.setBarberStatus(st, { barberId: "b1", status: "idle" }), /服务中的单/);
  await od.transitionOrder(st, { orderId: r.order._id, to: "completed" }, clock);
  await od.setBarberStatus(st, { barberId: "b1", status: "rest" });
  assert.equal((await st.getBarber("b1")).status, "rest");
});

test("统计：按项目/属性/收入/均耗时聚合，只算已完成的单", async () => {
  const st = setup();
  const rows = [["x1", "s1", "woman", 30 * MIN], ["x2", "s1", "woman", 50 * MIN], ["x3", "s2", "elder", 120 * MIN]];
  for (const [cid, item, type, dur] of rows) {
    const r = await od.createOrder(st, { barberId: "b1", serviceItemId: item, customerOpenid: cid, customerType: type }, clock);
    await od.transitionOrder(st, { orderId: r.order._id, to: "serving" }, clock);
    clk += dur;
    await od.transitionOrder(st, { orderId: r.order._id, to: "completed" }, clock);
  }
  const s = await od.aggregateStats(st, { barberId: "b1", fromTs: 0, toTs: clk + HOUR });
  assert.equal(s.completedCount, 3);
  assert.equal(s.byServiceCount["剪发"], 2);
  assert.equal(s.byService["剪发"], 40 * MIN);
  assert.equal(s.byCustomerType["woman"], 2);
  assert.equal(s.revenue, 38 + 38 + 288);
  assert.equal(s.avgServiceMs, Math.round(((30 + 50 + 120) * MIN) / 3));
});
