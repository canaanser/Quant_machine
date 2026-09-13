// 一条命令看全流程（不需要微信环境）：node scripts/demo.cjs
const { makeStore } = require("../tests/mockstore.cjs");
const od = require("../shared/orders.js");

const HOUR = 3600e3, MIN = 60e3;
let now = 1789260000000;
const clock = () => now;
const t = (ts) => new Date(ts + 8 * HOUR).toISOString().slice(11, 16);

const st = makeStore({
  barbers: [{ _id: "b1", name: "阿明", status: "idle", currentOrderId: null }],
  serviceItems: [
    { _id: "s1", barberId: "b1", name: "剪发", defaultDuration: 40 * MIN, price: 38 },
    { _id: "s2", barberId: "b1", name: "烫发", defaultDuration: 150 * MIN, price: 288 },
  ],
  orders: [],
});

const show = async (label) => {
  const q = await od.queueView(st, "b1", now);
  const b = await st.getBarber("b1");
  console.log(`\n【${label}】理发师=${b.status}`);
  console.log("  排队序：" + (q.length ? q.map((o, i) => `${i + 1}.${o.customerName}(${["预付款", "已预约", "现场"][o.priority]})`).join("  ") : "（空）"));
};

(async () => {
  console.log("=== 理发师接单/排队系统 · 全流程演示（与线上同一份逻辑）===");
  let r = await od.createOrder(st, { barberId: "b1", serviceItemId: "s1", customerOpenid: "w1", customerName: "张叔", customerType: "elder" }, clock);
  console.log(`① ${t(now)} 张叔到店（现场）→ ${r.order.status}`);
  now += 5 * MIN;
  await od.createOrder(st, { barberId: "b1", serviceItemId: "s1", customerOpenid: "w2", customerName: "小王", customerType: "woman", isPrepaid: true }, clock);
  console.log(`② ${t(now)} 小王到店（现场·已预付）`);
  await show("此刻排队（预付款插到同段前面）");
  now += 5 * MIN;
  await od.createOrder(st, { barberId: "b1", serviceItemId: "s2", customerOpenid: "c9", customerName: "李姐", customerType: "woman", appointmentTime: now + HOUR }, clock);
  console.log(`③ ${t(now)} 李姐预约 ${t(now + HOUR)} 烫发（未到点，不该插到现场客人前面）`);
  await show("加上预约之后");

  const q = await od.queueView(st, "b1", now);
  const first = q[0];
  await od.transitionOrder(st, { orderId: first._id, to: "serving" }, clock);
  console.log(`\n④ ${t(now)} 开始服务：${first.customerName}`);
  const reserved = (await st.listOrders("b1")).find((o) => o.status === "reserved");
  try { await od.transitionOrder(st, { orderId: reserved._id, to: "completed" }, clock); }
  catch (e) { console.log("   跳级被拒：" + e.message); }
  now += 40 * MIN;
  await od.transitionOrder(st, { orderId: first._id, to: "completed" }, clock);
  console.log(`⑤ ${t(now)} 完成本单`);
  await show("完成后");

  const s = await od.aggregateStats(st, { barberId: "b1", fromTs: 0, toTs: now + HOUR });
  console.log(`\n⑥ 统计：${s.completedCount} 单｜收入 ¥${s.revenue}｜均耗时 ${Math.round(s.avgServiceMs / MIN)} 分钟｜按项目 ${JSON.stringify(s.byServiceCount)}`);

  const dup = { barberId: "b1", serviceItemId: "s1", customerOpenid: "dup", appointmentTime: now + 3 * HOUR };
  const a = await od.createOrder(st, dup, clock);
  const b = await od.createOrder(st, dup, clock);
  console.log(`\n⑦ 防双击：第一次 created=${a.created}｜第二次 created=${b.created}｜同一单号=${a.order._id === b.order._id}`);

  await od.setBarberStatus(st, { barberId: "b1", status: "rest" });
  console.log("\n⑧ 切「休息」→ 顾客端会显示'休息中，暂不接单'");
  console.log("\n=== 演示结束 ===");
})();
