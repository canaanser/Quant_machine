// 两端联动预览：**直接 import 真实的 shared/ 逻辑**（不是另写一份假界面）。
// 关键改动（2026-09-14，老板反馈"按钮没反应/只有一端"）：
//   ① 事件用**委托**挂在 document 上、按 data-act 分发 —— 重渲染不会丢监听；
//   ② 每次操作都 try/catch，**错误直接显示在页面顶部**（不再"按了没反应"）；
//   ③ 左右两端**同一份 store**，任何动作后两端一起重绘。
import { makeStore } from "../tests/mockstore.mjs";
import { createOrder, transitionOrder, setBarberStatus, aggregateStats, queueView } from "../shared/orders.js";

const HOUR = 3600e3, MIN = 60e3;
const TYPES = [{ k: "woman", l: "女士 👩" }, { k: "man", l: "男士 👨" }, { k: "elder", l: "老人 🧓" }, { k: "child", l: "小孩 🧒" }];
const PNAME = ["预付款", "已预约", "现场"];

let now = Date.now();
const clock = () => now;
const store = makeStore({
  barbers: [{ _id: "b1", name: "阿明", status: "idle", currentOrderId: null }],
  serviceItems: [
    { _id: "s1", barberId: "b1", name: "剪发", defaultDuration: 40 * MIN, price: 38 },
    { _id: "s2", barberId: "b1", name: "烫发", defaultDuration: 150 * MIN, price: 288 },
    { _id: "s3", barberId: "b1", name: "染发", defaultDuration: 120 * MIN, price: 258 },
  ],
  orders: [],
});

const ui = { cust: "home", step: 1, slot: null, item: null, type: null, picked: null, itemPicked: null };
const t = (ts) => (ts ? new Date(ts).toTimeString().slice(0, 5) : "--:--");
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function showErr(e) {
  const box = $("err");
  box.hidden = false;
  box.textContent = "操作出错（把这段发我即可）：" + (e && (e.message || e));
}
const clearErr = () => { $("err").hidden = true; };

function statusCard(barber, queue) {
  const tone = barber.status === "idle" ? "free" : barber.status === "busy" ? "busy" : "rest";
  const text = barber.status === "idle" ? "空闲中，可立即到店"
    : barber.status === "busy" ? "正在服务中（预计还需 20 分钟）" : "休息中，暂不接单";
  return `<div class="status ${tone}">
      <div class="big">${text}</div>
      <div class="small">前面还有 ${queue.length} 位 · 更新于 ${t(now)}</div>
    </div>`;
}

async function renderCustomer() {
  const barber = await store.getBarber("b1");
  const queue = await queueView(store, "b1", now);
  const mine = (await store.listOrders("b1")).filter((o) => o.customerOpenid === "me" && !["completed", "cancelled"].includes(o.status)).pop();
  const items = store._data.serviceItems;
  const ahead = mine ? queue.findIndex((o) => o._id === mine._id) : -1;
  let html = statusCard(barber, queue.filter((o) => o.customerOpenid !== "me"));

  if (ui.cust === "home") {
    html += `<div class="card">
      <button class="btn primary" data-act="toBook">立即预约</button>
      <button class="btn ghost" data-act="join">加入排队（现在就到店）</button>
    </div>
    <div class="card sub">说明：预付款用户<b>仅在同一时间段内</b>优先，不跨时段插队。</div>`;
    if (mine) {
      html += `<div class="card"><div class="title">我的单</div>
        <div class="item"><span>${esc(mine.serviceName)} · ${esc(mine.status)}</span><span class="pill">${PNAME[mine.priority]}</span></div>
        <div class="sub">${mine.status === "serving" ? "现在轮到你，正在服务"
          : "预计 " + t(mine.appointmentTime || now + 20 * MIN) + " 轮到你（前面 ${ahead < 0 ? 0 : ahead} 位）"}</div></div>`;
    }
  } else if (ui.cust === "book") {
    const base = new Date(now); base.setMinutes(0, 0, 0);
    const slots = [];
    for (let i = 1; i <= 6; i++) {
      const ts = base.getTime() + i * 40 * MIN;
      slots.push({ ts, busy: queue.some((o) => o.appointmentTime && Math.abs(o.appointmentTime - ts) < 20 * MIN) });
    }
    html += `<div class="card">
      <div class="title">预约 · 第 ${ui.step} / 3 步</div>
      ${ui.step === 1 ? `<div class="sub" style="margin-top:8px">选时间（绿=可约，灰=已约）</div>
        <div class="chips">${slots.map((s) => `<div class="chip slot ${s.busy ? "busy" : "free"} ${ui.slot === s.ts ? "on" : ""}" data-act="slot" data-ts="${s.ts}">${t(s.ts)}</div>`).join("")}</div>` : ""}
      ${ui.step === 2 ? `<div class="sub" style="margin-top:8px">选项目</div>
        ${items.map((i) => `<div class="item" data-act="item" data-id="${i._id}" style="cursor:pointer"><span>${i.name}</span><span>¥${i.price} · ${i.defaultDuration / MIN} 分钟</span></div>`).join("")}` : ""}
      ${ui.step === 3 ? `<div class="sub" style="margin-top:8px">选客人属性</div>
        <div class="chips">${TYPES.map((x) => `<div class="chip ${ui.type === x.k ? "on" : ""}" data-act="type" data-k="${x.k}">${x.l}</div>`).join("")}</div>
        <button class="btn primary" data-act="submit">确认预约</button>` : ""}
      <button class="btn ghost" data-act="home">返回首页</button>
    </div>`;
  }
  $("screen-customer").innerHTML = html;
}

async function renderBarber() {
  const barber = await store.getBarber("b1");
  const queue = await queueView(store, "b1", now);
  const serving = (await store.listOrders("b1")).find((o) => o.status === "serving");
  const s = await aggregateStats(store, { barberId: "b1", fromTs: 0, toTs: Number.MAX_SAFE_INTEGER });
  const items = store._data.serviceItems;

  $("screen-barber").innerHTML = `
    <div class="card">
      <div class="row"><div class="title">当前服务</div><span class="sub">${barber.status === "busy" ? "服务中" : barber.status === "idle" ? "空闲" : "休息"}</span></div>
      <div class="sub" style="margin-top:6px">${serving ? esc(serving.customerName) + " · " + esc(serving.serviceName) + "（" + t(serving.actualStartTime) + " 开始）" : "现在没有在服务的客人"}</div>
      <button class="btn primary" data-act="finish" ${serving ? "" : "disabled style='opacity:.45'"}>完成本单</button>
    </div>
    <div class="card">
      <div class="title">一键状态</div>
      <div class="chips">
        <div class="chip ${barber.status === "idle" ? "on" : ""}" data-act="st" data-s="idle">空闲</div>
        <div class="chip ${barber.status === "busy" ? "on" : ""}" data-act="st" data-s="busy">忙</div>
        <div class="chip ${barber.status === "rest" ? "on" : ""}" data-act="st" data-s="rest">休息</div>
      </div>
    </div>
    <div class="card">
      <div class="title">快捷接单（≤3 击）</div>
      <div class="sub">1 选客人 → 2 选项目 → 3 开始服务</div>
      <div class="chips">${TYPES.map((x) => `<div class="chip ${ui.picked === x.k ? "on" : ""}" data-act="pk" data-k="${x.k}">${x.l}</div>`).join("")}</div>
      <div class="chips">${items.map((i) => `<div class="chip ${ui.itemPicked === i._id ? "on" : ""}" data-act="pi" data-id="${i._id}">${i.name}</div>`).join("")}</div>
      <button class="btn primary" data-act="start">开始服务</button>
    </div>
    <div class="card">
      <div class="title">排队列表（预付款同段优先）</div>
      ${queue.length ? queue.map((o, i) => `<div class="item"><span>${i + 1}. ${esc(o.customerName || "顾客")} · ${esc(o.serviceName)}</span><span class="pill">${PNAME[o.priority]}</span></div>`).join("") : `<div class="empty">暂无排队</div>`}
    </div>
    <div class="card">
      <div class="title">统计</div>
      <div class="item"><span>已完成</span><span>${s.completedCount} 单</span></div>
      <div class="item"><span>收入</span><span>¥${s.revenue}</span></div>
      <div class="item"><span>平均耗时</span><span>${Math.round(s.avgServiceMs / MIN)} 分钟</span></div>
      <div class="sub">按项目 ${esc(JSON.stringify(s.byServiceCount))}｜按客人 ${esc(JSON.stringify(s.byCustomerType))}</div>
    </div>`;
}

async function renderAll() {
  try { await renderCustomer(); await renderBarber(); }
  catch (e) { showErr(e); }
}

// ── 事件委托：一次挂载，永不丢 ──────────────────────────────────────────────
document.addEventListener("click", async (ev) => {
  const el = ev.target.closest("[data-act]");
  if (!el) return;
  try {
    clearErr();
    const act = el.dataset.act;
    if (act === "toBook") { ui.cust = "book"; ui.step = 1; }
    else if (act === "home") { ui.cust = "home"; }
    else if (act === "slot") { ui.slot = Number(el.dataset.ts); ui.step = 2; }
    else if (act === "item") { ui.item = el.dataset.id; ui.step = 3; }
    else if (act === "type") { ui.type = el.dataset.k; }
    else if (act === "submit") {
      await createOrder(store, { barberId: "b1", serviceItemId: ui.item, customerOpenid: "me", customerName: "我（顾客）", customerType: ui.type, appointmentTime: ui.slot }, clock);
      ui.cust = "home";
    } else if (act === "join") {
      await createOrder(store, { barberId: "b1", serviceItemId: "s1", customerOpenid: "me", customerName: "我（顾客）", customerType: "man" }, clock);
    } else if (act === "pk") { ui.picked = el.dataset.k; }
    else if (act === "pi") { ui.itemPicked = el.dataset.id; }
    else if (act === "start") {
      if (!ui.picked || !ui.itemPicked) throw new Error("先点一个「客人类型」，再点一个「项目」，最后点「开始服务」");
      const r = await createOrder(store, { barberId: "b1", serviceItemId: ui.itemPicked, customerOpenid: "walk_" + now, customerName: "现场客", customerType: ui.picked }, clock);
      await transitionOrder(store, { orderId: r.order._id, to: "serving" }, clock);
      ui.picked = null; ui.itemPicked = null;
    } else if (act === "finish") {
      const serving = (await store.listOrders("b1")).find((o) => o.status === "serving");
      if (serving) { await transitionOrder(store, { orderId: serving._id, to: "completed" }, clock); now += 40 * MIN; }
    } else if (act === "st") { await setBarberStatus(store, { barberId: "b1", status: el.dataset.s }); }
    else if (act === "demo") {
      const base = new Date(now); base.setMinutes(0, 0, 0);
      const r1 = await createOrder(store, { barberId: "b1", serviceItemId: "s1", customerOpenid: "me", customerName: "我（顾客）", customerType: "woman", appointmentTime: base.getTime() + 40 * MIN }, clock);
      ui.cust = "home";
      await transitionOrder(store, { orderId: r1.order._id, to: "queuing" }, clock);
      await transitionOrder(store, { orderId: r1.order._id, to: "serving" }, clock);
      await transitionOrder(store, { orderId: r1.order._id, to: "completed" }, clock);
      now += 40 * MIN;
    }
    await renderAll();
  } catch (e) { showErr(e); await renderAll(); }
});

renderAll();
