// 订单/调度领域的**全部业务逻辑**（唯一真源，CommonJS；云函数只是薄壳）。
const { assertTransition, isTerminal } = require("./statemachine.js");
const { normalizePriority, sortQueue, activeOrders } = require("./priority.js");
const { hasConflict } = require("./slots.js");

const now = (clock) => (typeof clock === "function" ? clock() : Date.now());

async function createOrder(store, payload, clock) {
  const p = payload || {};
  const barber = await store.getBarber(p.barberId);
  if (!barber) throw new Error("理发师不存在：" + p.barberId);
  const item = await store.getItem(p.serviceItemId);
  if (!item) throw new Error("服务项目不存在：" + p.serviceItemId);
  if (!p.customerOpenid) throw new Error("缺少 customerOpenid");

  const ts = now(clock);
  const duration = Number(p.duration || item.defaultDuration || 0);
  const appointmentTime = Number(p.appointmentTime || 0);
  const isPrepaid = !!p.isPrepaid;
  const existing = await store.listOrders(p.barberId);

  // ★ 幂等检查必须在冲突检查之前（否则重放请求会被自己的第一单判成时段占用）
  const dup = existing.find((o) => o.customerOpenid === p.customerOpenid &&
    o.serviceItemId === p.serviceItemId && Number(o.appointmentTime || 0) === appointmentTime &&
    !isTerminal(o.status) && ts - Number(o.createdAt || 0) < 60 * 1000);
  if (dup) return { order: dup, created: false };

  if (appointmentTime > 0 && hasConflict(appointmentTime, duration, existing)) {
    throw new Error("该时段已被占用，请另选时间");
  }

  const order = {
    _id: p._id || ("o_" + p.barberId + "_" + ts + "_" + Math.random().toString(36).slice(2, 6)),
    barberId: p.barberId,
    customerOpenid: p.customerOpenid,
    customerName: p.customerName || "",
    customerType: p.customerType || "man",
    serviceItemId: item._id,
    serviceName: item.name,
    price: Number(item.price || 0),          // 快照单价：以后改价不影响历史收入
    duration,
    priority: isPrepaid ? 0 : (appointmentTime > 0 ? 1 : 2),
    status: appointmentTime > 0 ? "reserved" : "queuing",
    appointmentTime,
    actualStartTime: 0,
    actualEndTime: 0,
    isPrepaid,
    prepaidAmount: Number(p.prepaidAmount || 0),
    createdAt: ts,
    updatedAt: ts,
  };
  await store.insertOrder(order);
  return { order, created: true };
}

async function transitionOrder(store, payload, clock) {
  const p = payload || {};
  const order = await store.getOrder(p.orderId);
  if (!order) throw new Error("订单不存在：" + p.orderId);
  if (isTerminal(order.status)) throw new Error("终态订单不可再变更：" + order.status);
  if (order.status === p.to) return { order, changed: false };
  if (p.expectedUpdatedAt && Number(p.expectedUpdatedAt) !== Number(order.updatedAt)) {
    throw new Error("订单已被他人更新（乐观锁失败），请刷新后重试");
  }
  assertTransition(order.status, p.to);

  const ts = now(clock);
  const patch = { status: p.to, updatedAt: ts };
  if (p.to === "serving") patch.actualStartTime = ts;
  if (p.to === "completed") patch.actualEndTime = ts;
  await store.updateOrder(order._id, patch, order.updatedAt);

  const barberPatch = {};
  if (p.to === "serving") { barberPatch.status = "busy"; barberPatch.currentOrderId = order._id; }
  if (p.to === "completed" || p.to === "cancelled") {
    const barber = await store.getBarber(order.barberId);
    if (barber && barber.currentOrderId === order._id) { barberPatch.status = "idle"; barberPatch.currentOrderId = null; }
  }
  if (Object.keys(barberPatch).length) await store.updateBarber(order.barberId, barberPatch);
  return { order: Object.assign({}, order, patch), changed: true };
}

async function setBarberStatus(store, payload) {
  const p = payload || {};
  if (!["idle", "busy", "rest"].includes(p.status)) throw new Error("非法状态：" + p.status);
  const barber = await store.getBarber(p.barberId);
  if (!barber) throw new Error("理发师不存在：" + p.barberId);
  if (p.status === "idle" && barber.currentOrderId) throw new Error("手上还有服务中的单，先「完成」再切空闲");
  await store.updateBarber(p.barberId, { status: p.status });
  return { barberId: p.barberId, status: p.status };
}

async function aggregateStats(store, payload) {
  const p = payload || {};
  const all = await store.listOrders(p.barberId);
  const done = all.filter((o) => o.status === "completed" &&
    Number(o.actualEndTime || 0) >= Number(p.fromTs || 0) &&
    Number(o.actualEndTime || 0) <= Number(p.toTs || 0 || Number.MAX_SAFE_INTEGER));

  const byService = {}, byCustomerType = {}, byDay = {};
  let revenue = 0, totalDuration = 0;
  for (const o of done) {
    const dur = Math.max(0, Number(o.actualEndTime || 0) - Number(o.actualStartTime || 0));
    revenue += Number(o.price || 0); totalDuration += dur;
    const s = byService[o.serviceName] = byService[o.serviceName] || { count: 0, totalDuration: 0 };
    s.count++; s.totalDuration += dur;
    byCustomerType[o.customerType] = (byCustomerType[o.customerType] || 0) + 1;
    const day = new Date(Number(o.actualEndTime || 0) + 8 * 3600e3).toISOString().slice(0, 10);
    byDay[day] = (byDay[day] || 0) + 1;
  }
  const avgMs = {};
  for (const k of Object.keys(byService)) avgMs[k] = Math.round(byService[k].totalDuration / Math.max(1, byService[k].count));
  return {
    completedCount: done.length, revenue,
    avgServiceMs: done.length ? Math.round(totalDuration / done.length) : 0,
    byService: avgMs,
    byServiceCount: Object.fromEntries(Object.entries(byService).map(([k, v]) => [k, v.count])),
    byCustomerType, byDay,
  };
}

async function queueView(store, barberId, nowTs) {
  const orders = await store.listOrders(barberId);
  return sortQueue(activeOrders(orders), nowTs);
}

module.exports = { createOrder, transitionOrder, setBarberStatus, aggregateStats, queueView, normalizePriority };
