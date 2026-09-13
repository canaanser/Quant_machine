// 一条命令看全流程：node scripts/demo.mjs
// 用内存 store 跑真实业务逻辑（shared/orders.js），把每一步的状态变化、排队序、统计打出来。
// 目的：不用微信开发者工具、不用云环境，也能"看见"这套系统在工作。
import { makeStore } from "../tests/mockstore.mjs";
import { createOrder, transitionOrder, setBarberStatus, aggregateStats, queueView } from "../shared/orders.js";

const HOUR = 3600 * 1000;
const MIN = 60 * 1000;
let now = 1789260000000;                    // 固定基准：2026-09-13 22:00 (+08)
const clock = () => now;
const t = (ts) => new Date(ts + 8 * HOUR).toISOString().slice(11, 16);
const line = (s) => console.log(s);

const store = makeStore({
  barbers: [{ _id: "b1", name: "阿明", status: "idle", currentOrderId: null }],
  serviceItems: [
    { _id: "s1", barberId: "b1", name: "剪发", defaultDuration: 40 * MIN, price: 38 },
    { _id: "s2", barberId: "b1", name: "烫发", defaultDuration: 150 * MIN, price: 288 },
  ],
  orders: [],
});

const show = async (label) => {
  const q = await queueView(store, "b1", now);
  const b = await store.getBarber("b1");
  line(`\n【${label}】理发师=${b.status}${b.currentOrderId ? "（服务中）" : ""}`);
  line("  排队序：" + (q.length ? q.map((o, i) => `${i + 1}.${o.customerName}(${o.serviceName}/${["预付款", "已预约", "现场"][o.priority]})`).join("  ") : "（空）"));
};

line("=== 理发师接单/排队系统 · 本地全流程演示 ===");
line(`起点：${t(now)} 阿明=空闲`);

// 1) 现场客人（普通）
let r = await createOrder(store, { barberId: "b1", serviceItemId: "s1", customerOpenid: "w1", customerName: "张叔", customerType: "elder" }, clock);
line(`\n① ${t(now)} 张叔到店（现场排队）→ 单号 ${r.order._id.slice(-6)}，状态=${r.order.status}`);

// 2) 第二个现场客人，预付款 → 应排到张叔前面（同段内预付款优先）
now += 5 * MIN;
r = await createOrder(store, { barberId: "b1", serviceItemId: "s1", customerOpenid: "w2", customerName: "小王", customerType: "woman", isPrepaid: true }, clock);
line(`② ${t(now)} 小王到店（现场·已预付）→ 状态=${r.order.status}`);
await show("此刻排队");

// 3) 预约一小时后烫发
now += 5 * MIN;
const bk = now + HOUR;
r = await createOrder(store, { barberId: "b1", serviceItemId: "s2", customerOpenid: "c9", customerName: "李姐", customerType: "woman", appointmentTime: bk }, clock);
line(`\n③ ${t(now)} 李姐预约 ${t(bk)} 烫发 → 状态=${r.order.status}（预约未到点，不该插到现场客人前面）`);
await show("加上预约之后");

// 4) 开始服务（预约单不许跳级直接完成）
const q = await queueView(store, "b1", now);
const first = q[0];
line(`\n④ ${t(now)} 开始服务：${first.customerName}`);
await transitionOrder(store, { orderId: first._id, to: "serving" }, clock);
await show("服务中");
line(`   试一下跳级：把「还没开始服务」的预约单（李姐）直接标成已完成——`);
const reserved = (await store.listOrders("b1")).find((o) => o.status === "reserved");
try { await transitionOrder(store, { orderId: reserved._id, to: "completed" }, clock); }
catch (e) { line("   被拒：" + e.message + "（必须先 serving）"); }

// 5) 完成
now += 40 * MIN;
await transitionOrder(store, { orderId: first._id, to: "completed" }, clock);
line(`\n⑤ ${t(now)} 完成本单（耗时 40 分钟）`);
await show("完成后");

// 6) 统计
const s = await aggregateStats(store, { barberId: "b1", fromTs: 0, toTs: now + HOUR });
line(`\n⑥ 统计：完成 ${s.completedCount} 单｜收入 ¥${s.revenue}｜平均耗时 ${Math.round(s.avgServiceMs / MIN)} 分钟`);
line(`   按客人属性：${JSON.stringify(s.byCustomerType)}｜按项目：${JSON.stringify(s.byServiceCount)}`);

// 7) 幂等演示
line("\n⑦ 防双击演示（同一分钟内重复提交同一个预约）——");
const dupPayload = { barberId: "b1", serviceItemId: "s1", customerOpenid: "dup1", customerName: "双击客", appointmentTime: now + 3 * HOUR };
const first1 = await createOrder(store, dupPayload, clock);
const first2 = await createOrder(store, dupPayload, clock);          // 同一分钟、同参数
const before = (await store.listOrders("b1")).length;
line(`   第一次 created=${first1.created}｜第二次 created=${first2.created}｜单号相同=${first1.order._id === first2.order._id}`);
line(`   库里当前单数=${before}（若重复提交真的产生了第二单，这里会增加）`);

// 8) 理发师切状态
await setBarberStatus(store, { barberId: "b1", status: "rest" });
line(`\n⑧ ${t(now)} 阿明切「休息」→ 顾客端首页会立刻显示"休息中，暂不接单"`);
line("\n=== 演示结束（以上每一步都由 shared/orders.js 的真实逻辑驱动，与线上同一份代码）===");
