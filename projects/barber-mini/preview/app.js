// 浏览器预览：**直接 import 真实的 shared/ 逻辑**（不是另写一份假界面）
import { makeStore } from "../tests/mockstore.mjs";
import { createOrder, transitionOrder, setBarberStatus, aggregateStats, queueView } from "../shared/orders.js";

const HOUR = 3600 * 1000, MIN = 60 * 1000;
const TYPES = [{ k: "woman", l: "女士 👩" }, { k: "man", l: "男士 👨" }, { k: "elder", l: "老人 🧓" }, { k: "child", l: "小孩 🧒" }];

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

const ui = { tab: "customer", cust: "home", step: 1, slot: null, item: null, type: null, picked: null, itemPicked: null, err: "" };
const screen = document.getElementById("screen");
const t = (ts) => new Date(ts).toTimeString().slice(0, 5);

async function render() {
  const barber = await store.getBarber("b1");
  const queue = await queueView(store, "b1", now);
  const myOrder = (await store.listOrders("b1")).find((o) => o.customerOpenid === "me" && !["completed", "cancelled"].includes(o.status));
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === ui.tab));

  if (ui.tab === "customer") {
    if (ui.cust === "home") {
      screen.innerHTML = `
        <div class="status ${barber.status === "idle" ? "free" : barber.status === "busy" ? "busy" : "rest"}">
          <div class="big">${barber.status === "idle" ? "空闲中，可立即到店" : barber.status === "busy" ? "正在服务中（预计还需 20 分钟）" : "休息中，暂不接单"}</div>
          <div class="small">前面还有 ${Math.max(0, queue.filter((o) => o.priority > 0).length)} 位 · 更新于 ${t(now)}</div>
        </div>
        <div class="card">
          <button class="btn primary" id="toBook">立即预约</button>
          <button class="btn ghost" id="join">加入排队（现场）</button>
        </div>
        <div class="card sub">说明：预付款用户<b>仅在同一时间段内</b>优先，不跨时段插队。</div>
        ${myOrder ? `<div class="card"><div class="title">我的单</div><div class="item"><span>${myOrder.serviceName} · ${myOrder.status}</span><span class="pill">${["预付款", "已预约", "现场"][myOrder.priority]}</span></div><div class="sub">预计 ${t(myOrder.appointmentTime || now + 30 * MIN)} 轮到你</div></div>` : ""}
      `;
      document.getElementById("toBook").onclick = () => { ui.cust = "book"; ui.step = 1; render(); };
      document.getElementById("join").onclick = async () => {
        await createOrder(store, { barberId: "b1", serviceItemId: "s1", customerOpenid: "me", customerName: "我", customerType: "man" }, clock);
        ui.cust = "progress"; render();
      };
    } else if (ui.cust === "book") {
      const slots = [];
      const base = new Date(now); base.setMinutes(0, 0, 0);
      for (let i = 1; i <= 8; i++) slots.push({ ts: base.getTime() + i * 40 * MIN, busy: queue.some((o) => Math.abs((o.appointmentTime || 0) - (base.getTime() + i * 40 * MIN)) < 20 * MIN) });
      const items = (await store._data.serviceItems);
      screen.innerHTML = `
        <div class="card">
          <div class="title">预约 · 第 ${ui.step} / 3 步</div>
          ${ui.step === 1 ? `<div class="sub" style="margin-top:8px">选时间（绿=可约，灰=已约）</div><div class="chips" style="margin-top:10px">${slots.map((s) => `<div class="slot ${s.busy ? "busy" : "free"} ${ui.slot === s.ts ? "on" : ""}" data-slot="${s.ts}">${t(s.ts)}</div>`).join("")}</div>` : ""}
          ${ui.step === 2 ? `<div class="sub" style="margin-top:8px">选项目</div>${items.map((i) => `<div class="item" data-item="${i._id}" style="cursor:pointer"><span>${i.name}</span><span>¥${i.price} · ${i.defaultDuration / MIN}分</span></div>`).join("")}` : ""}
          ${ui.step === 3 ? `<div class="sub" style="margin-top:8px">选客人属性</div><div class="chips">${TYPES.map((x) => `<div class="chip ${ui.type === x.k ? "on" : ""}" data-type="${x.k}">${x.l}</div>`).join("")}</div><button class="btn primary" id="ok">确认预约</button>` : ""}
          <button class="btn ghost sm" id="back">返回</button>
          ${ui.err ? `<div class="sub" style="color:#D93A3A;margin-top:8px">${ui.err}</div>` : ""}
        </div>`;
      screen.querySelectorAll("[data-slot]").forEach((el) => el.onclick = () => { ui.slot = Number(el.dataset.slot); ui.step = 2; render(); });
      screen.querySelectorAll("[data-item]").forEach((el) => el.onclick = () => { ui.item = el.dataset.item; ui.step = 3; render(); });
      screen.querySelectorAll("[data-type]").forEach((el) => el.onclick = () => { ui.type = el.dataset.type; render(); });
      if (document.getElementById("ok")) document.getElementById("ok").onclick = async () => {
        try {
          await createOrder(store, { barberId: "b1", serviceItemId: ui.item, customerOpenid: "me", customerName: "我", customerType: ui.type, appointmentTime: ui.slot }, clock);
          ui.cust = "home"; ui.err = ""; render();
        } catch (e) { ui.err = e.message; render(); }
      };
      document.getElementById("back").onclick = () => { ui.cust = "home"; render(); };
    } else {
      const q = await queueView(store, "b1", now);
      const ahead = q.findIndex((o) => o.customerOpenid === "me");
      screen.innerHTML = `<div class="card">
        <div class="title">前面还有 ${ahead < 0 ? 0 : ahead} 位</div>
        <div style="font-size:40px;font-weight:700;color:var(--gold);margin-top:12px">${ahead < 0 ? "已轮到你" : (ahead * 20) + " 分钟"}</div>
        <div class="sub" style="margin-top:10px">实时更新（云环境里由 watch 推送；这里是本地即时计算）</div>
        <button class="btn ghost sm" id="back">返回首页</button></div>`;
      document.getElementById("back").onclick = () => { ui.cust = "home"; render(); };
    }
  } else {
    const serving = (await store.listOrders("b1")).find((o) => o.status === "serving");
    const s = await aggregateStats(store, { barberId: "b1", fromTs: 0, toTs: Number.MAX_SAFE_INTEGER });
    screen.innerHTML = `
      <div class="card">
        <div class="row"><div class="title">当前服务</div><span class="sub">${barber.status === "busy" ? "服务中" : barber.status === "idle" ? "空闲" : "休息"}</span></div>
        <div class="sub" style="margin-top:6px">${serving ? serving.customerName + " · " + serving.serviceName : "现在没有在服务的客人"}</div>
        <button class="btn primary" id="done" ${serving ? "" : "disabled style='opacity:.5'"}>完成本单</button>
      </div>
      <div class="card">
        <div class="title">一键状态</div>
        <div class="chips">
          <div class="chip ${barber.status === "idle" ? "on" : ""}" data-st="idle">空闲</div>
          <div class="chip ${barber.status === "busy" ? "on" : ""}" data-st="busy">忙</div>
          <div class="chip ${barber.status === "rest" ? "on" : ""}" data-st="rest">休息</div>
        </div>
      </div>
      <div class="card">
        <div class="title">快捷接单（≤3 击）</div>
        <div class="sub">1 选客人 → 2 选项目 → 3 开始</div>
        <div class="chips">${TYPES.map((x) => `<div class="chip ${ui.picked === x.k ? "on" : ""}" data-pk="${x.k}">${x.l}</div>`).join("")}</div>
        <div class="chips">${(await store._data.serviceItems).map((i) => `<div class="chip ${ui.itemPicked === i._id ? "on" : ""}" data-pi="${i._id}">${i.name}</div>`).join("")}</div>
        <button class="btn primary" id="start">开始服务</button>
        ${ui.err ? `<div class="sub" style="color:#D93A3A;margin-top:8px">${ui.err}</div>` : ""}
      </div>
      <div class="card">
        <div class="title">排队列表（预付款同段优先）</div>
        ${queue.length ? queue.map((o, i) => `<div class="item"><span>${i + 1}. ${o.customerName} · ${o.serviceName}</span><span class="pill">${["预付款", "已预约", "现场"][o.priority]}</span></div>`).join("") : `<div class="sub">暂无排队</div>`}
      </div>
      <div class="card">
        <div class="title">统计</div>
        <div class="item"><span>已完成</span><span>${s.completedCount} 单</span></div>
        <div class="item"><span>收入</span><span>¥${s.revenue}</span></div>
        <div class="item"><span>平均耗时</span><span>${Math.round(s.avgServiceMs / MIN)} 分钟</span></div>
        <div class="sub">按项目 ${JSON.stringify(s.byServiceCount)}｜按客人 ${JSON.stringify(s.byCustomerType)}</div>
      </div>`;
    const d = document.getElementById("done");
    if (d) d.onclick = async () => { await transitionOrder(store, { orderId: serving._id, to: "completed" }, clock); now += 40 * MIN; render(); };
    screen.querySelectorAll("[data-st]").forEach((el) => el.onclick = async () => {
      try { await setBarberStatus(store, { barberId: "b1", status: el.dataset.st }); ui.err = ""; } catch (e) { ui.err = e.message; }
      render();
    });
    screen.querySelectorAll("[data-pk]").forEach((el) => el.onclick = () => { ui.picked = el.dataset.pk; render(); });
    screen.querySelectorAll("[data-pi]").forEach((el) => el.onclick = () => { ui.itemPicked = el.dataset.pi; render(); });
    document.getElementById("start").onclick = async () => {
      try {
        const r = await createOrder(store, { barberId: "b1", serviceItemId: ui.itemPicked, customerOpenid: "walk_" + now, customerName: "现场客", customerType: ui.picked }, clock);
        await transitionOrder(store, { orderId: r.order._id, to: "serving" }, clock);
        ui.picked = null; ui.itemPicked = null; ui.err = "";
      } catch (e) { ui.err = e.message; }
      render();
    };
  }
}

document.querySelectorAll(".tab").forEach((b) => b.onclick = () => { ui.tab = b.dataset.tab; render(); });
render();
