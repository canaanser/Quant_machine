// 领域逻辑的判别性单测：跑在**内存 store** 上，不需要微信云环境。
import test from "node:test";
import assert from "node:assert/strict";
import { createOrder, transitionOrder, setBarberStatus, aggregateStats, queueView } from "../shared/orders.js";
import { makeStore } from "./mockstore.mjs";

const HOUR = 3600 * 1000;
const T0 = 1789260000000;
let clk = T0;
const clock = () => clk;
const reset = () => { clk = T0; };

async function setup() {
  reset();
  const store = makeStore({
    barbers: [{ _id: "b1", name: "阿明", status: "idle", currentOrderId: null }],
    serviceItems: [
      { _id: "s1", barberId: "b1", name: "剪发", defaultDuration: 40 * 60 * 1000, price: 38 },
      { _id: "s2", barberId: "b1", name: "烫发", defaultDuration: 150 * 60 * 1000, price: 288 },
    ],
    orders: [],
  });
  return store;
}

test("主链A：预约 → 开始服务 → 完成（理发师状态跟着走）", async () => {
  const store = await setup();
  const { order, created } = await createOrder(store, {
    barberId: "b1", serviceItemId: "s1", customerOpenid: "c1", customerName: "小王",
    customerType: "woman", appointmentTime: T0 + HOUR,
  }, clock);
  assert.equal(created, true);
  assert.equal(order.status, "reserved");
  assert.equal(order.priority, 1);

  clk = T0 + HOUR;
  await transitionOrder(store, { orderId: order._id, to: "queuing", expectedUpdatedAt: order.updatedAt }, clock);
  clk += 60 * 1000;
  const serving = await transitionOrder(store, { orderId: order._id, to: "serving" }, clock);
  assert.equal(serving.order.actualStartTime, clk);
  assert.equal((await store.getBarber("b1")).status, "busy");
  assert.equal((await store.getBarber("b1")).currentOrderId, order._id);

  clk += 30 * 60 * 1000;
  await transitionOrder(store, { orderId: order._id, to: "completed" }, clock);
  const b = await store.getBarber("b1");
  assert.equal(b.status, "idle");
  assert.equal(b.currentOrderId, null);
});

test("主链B：现场排队（pending→queuing）→ 服务 → 完成；priority=2", async () => {
  const store = await setup();
  const { order } = await createOrder(store, {
    barberId: "b1", serviceItemId: "s1", customerOpenid: "c2", customerType: "man",
  }, clock);
  assert.equal(order.status, "queuing");
  assert.equal(order.priority, 2);
  await transitionOrder(store, { orderId: order._id, to: "serving" }, clock);
  clk += 40 * 60 * 1000;
  const done = await transitionOrder(store, { orderId: order._id, to: "completed" }, clock);
  assert.equal(done.order.status, "completed");
});

test("**幂等**：同请求重放不产生第二单；重复同向迁移不报错、不重复计时", async () => {
  const store = await setup();
  const payload = { barberId: "b1", serviceItemId: "s1", customerOpenid: "c9", appointmentTime: T0 + HOUR };
  const a = await createOrder(store, payload, clock);
  const b = await createOrder(store, payload, clock);
  assert.equal(a.created, true);
  assert.equal(b.created, false);
  assert.equal(b.order._id, a.order._id);
  assert.equal((await store.listOrders("b1")).length, 1);

  clk += 1000;
  const t1 = await transitionOrder(store, { orderId: a.order._id, to: "queuing" }, clock);
  const t2 = await transitionOrder(store, { orderId: a.order._id, to: "queuing" }, clock);
  assert.equal(t1.changed, true);
  assert.equal(t2.changed, false);
});

test("**非法迁移**被拒：reserved→completed 直接抛错（不许跳级）；终态不可再改", async () => {
  const store = await setup();
  const { order } = await createOrder(store, {
    barberId: "b1", serviceItemId: "s1", customerOpenid: "c3", appointmentTime: T0 + HOUR,
  }, clock);
  await assert.rejects(() => transitionOrder(store, { orderId: order._id, to: "completed" }, clock), /非法状态迁移/);
  await transitionOrder(store, { orderId: order._id, to: "queuing" }, clock);
  await transitionOrder(store, { orderId: order._id, to: "serving" }, clock);
  await transitionOrder(store, { orderId: order._id, to: "completed" }, clock);
  await assert.rejects(() => transitionOrder(store, { orderId: order._id, to: "serving" }, clock), /终态/);
});

test("**冲突**：同时段重复预约被拒；首尾相接不算冲突", async () => {
  const store = await setup();
  const dur = 40 * 60 * 1000;
  await createOrder(store, { barberId: "b1", serviceItemId: "s1", customerOpenid: "c1", appointmentTime: T0 + HOUR }, clock);
  await assert.rejects(() => createOrder(store, {
    barberId: "b1", serviceItemId: "s1", customerOpenid: "c2", appointmentTime: T0 + HOUR + 10 * 60 * 1000,
  }, clock), /已被占用/);
  const edge = await createOrder(store, {
    barberId: "b1", serviceItemId: "s1", customerOpenid: "c3", appointmentTime: T0 + HOUR + dur,
  }, clock);
  assert.equal(edge.created, true);   // 紧挨着下一单：可以
});

test("**乐观锁**：拿旧 updatedAt 提交被拒（防双击/防跨端覆盖）", async () => {
  const store = await setup();
  const { order } = await createOrder(store, { barberId: "b1", serviceItemId: "s1", customerOpenid: "c4", appointmentTime: T0 + HOUR }, clock);
  const stale = order.updatedAt;
  clk += 1000;
  await transitionOrder(store, { orderId: order._id, to: "queuing" }, clock);
  await assert.rejects(() => transitionOrder(store, { orderId: order._id, to: "cancelled", expectedUpdatedAt: stale }, clock), /乐观锁/);
});

test("**排队序**：现场单算「当前时段」——同段内预付款优先；未来时段的预约不许插到现场单前面", async () => {
  const store = await setup();
  const base = { barberId: "b1", serviceItemId: "s1" };
  await createOrder(store, { ...base, customerOpenid: "c1", appointmentTime: T0 + HOUR }, clock);                    // 1 小时后预约
  await createOrder(store, { ...base, customerOpenid: "c3", appointmentTime: T0 + 3 * HOUR, isPrepaid: true }, clock); // 3 小时后预约（预付款）
  await createOrder(store, { ...base, customerOpenid: "c4", isPrepaid: true }, clock);                                // 现场·预付款（当前时段）
  await createOrder(store, { ...base, customerOpenid: "c5" }, clock);                                                 // 现场·普通（当前时段）
  const q = await queueView(store, "b1", T0);
  assert.deepEqual(q.map((o) => o.customerOpenid), ["c4", "c5", "c1", "c3"]);
  // 现场组内：预付款(c4) 在普通(c5) 之前；未到点的预约(c1/c3) 排在后面——预付款 c3 也**不许**插到 c1 前面（跨段）
});

test("理发师状态：手上有单不许切空闲；完成最后一单后放回 idle", async () => {
  const store = await setup();
  const { order } = await createOrder(store, { barberId: "b1", serviceItemId: "s1", customerOpenid: "c5" }, clock);
  await transitionOrder(store, { orderId: order._id, to: "serving" }, clock);
  await assert.rejects(() => setBarberStatus(store, { barberId: "b1", status: "idle" }), /服务中的单/);
  await transitionOrder(store, { orderId: order._id, to: "completed" }, clock);
  await setBarberStatus(store, { barberId: "b1", status: "rest" });
  assert.equal((await store.getBarber("b1")).status, "rest");
});

test("统计：按项目/属性/天/收入聚合，只算已完成的单", async () => {
  const store = await setup();
  for (const [cid, item, dur] of [["x1", "s1", 30 * 60 * 1000], ["x2", "s1", 50 * 60 * 1000], ["x3", "s2", 120 * 60 * 1000]]) {
    const { order } = await createOrder(store, { barberId: "b1", serviceItemId: item, customerOpenid: cid, customerType: cid === "x3" ? "elder" : "woman" }, clock);
    await transitionOrder(store, { orderId: order._id, to: "serving" }, clock);
    clk += dur;
    await transitionOrder(store, { orderId: order._id, to: "completed" }, clock);
  }
  const s = await aggregateStats(store, { barberId: "b1", fromTs: T0 - HOUR, toTs: clk + HOUR });
  assert.equal(s.completedCount, 3);
  assert.equal(s.byServiceCount["剪发"], 2);
  assert.equal(s.byService["剪发"], 40 * 60 * 1000);        // 剪发两单 30+50 分钟 → 均值 40 分钟
  assert.equal(s.byService["烫发"], 120 * 60 * 1000);
  // 口径要对齐实现：**先把毫秒加起来再取整**（先取整分钟再换算会差 20 秒——我第一次就算错了）
  assert.equal(s.avgServiceMs, Math.round(((30 + 50 + 120) * 60 * 1000) / 3));
  assert.equal(s.byCustomerType["woman"], 2);
  assert.equal(s.byCustomerType["elder"], 1);
  assert.equal(s.revenue, 38 + 38 + 288);
});
