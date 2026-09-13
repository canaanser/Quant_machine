// 订单/调度领域的**全部业务逻辑**（唯一真源，云函数只是薄壳）。
// store 接口（由云函数或测试实现，逻辑本身不碰数据库）：
//   getBarber(id), getItem(id), listOrders(barberId), insertOrder(o), updateOrder(id, patch, expectUpdatedAt), updateBarber(id, patch)
import { assertTransition, isTerminal } from "./statemachine.js";
import { normalizePriority, sortQueue, activeOrders } from "./priority.js";
import { hasConflict } from "./slots.js";

const now = (clock) => (typeof clock === "function" ? clock() : Date.now());

/** 建单：预约（带 appointmentTime）或现场排队（不带）。冲突/时长以 serviceItem 为准。 */
export async function createOrder(store, payload, clock) {
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
  // ★ **幂等检查必须排在冲突检查之前**：重放同一请求时，否则第二单会被自己的第一单判成
  //   "时段已被占用"，永远走不到幂等分支（实测被单测抓红）。
  //   口径：同顾客 + 同时段 + 同项目，60 秒内重复提交 = 同一次（防双击/防重放）。
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
    price: Number(item.price || 0),          // ★ 快照单价：以后理发师改价，历史单的收入不变
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

/** 状态迁移：唯一写入口。带乐观锁（expectedUpdatedAt）+ 合法性校验 + 幂等。 */
export async function transitionOrder(store, payload, clock) {
  const p = payload || {};
  const order = await store.getOrder(p.orderId);
  if (!order) throw new Error("订单不存在：" + p.orderId);
  if (isTerminal(order.status)) throw new Error("终态订单不可再变更：" + order.status);
  if (order.status === p.to) return { order, changed: false };          // 幂等：重复同向请求直接返回
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
    // 只有"当前这单"结束才把理发师放回空闲（别的单在服务中就不动）
    const barber = await store.getBarber(order.barberId);
    if (barber && barber.currentOrderId === order._id) {
      barberPatch.status = "idle"; barberPatch.currentOrderId = null;
    }
  }
  if (Object.keys(barberPatch).length) await store.updateBarber(order.barberId, barberPatch);
  return { order: { ...order, ...patch }, changed: true };
}

/** 理发师手动切忙/闲/休息。 */
export async function setBarberStatus(store, payload) {
  const p = payload || {};
  if (!["idle", "busy", "rest"].includes(p.status)) throw new Error("非法状态：" + p.status);
  const barber = await store.getBarber(p.barberId);
  if (!barber) throw new Error("理发师不存在：" + p.barberId);
  if (p.status === "idle" && barber.currentOrderId) {
    throw new Error("手上还有服务中的单，先「完成」再切空闲");
  }
  await store.updateBarber(p.barberId, { status: p.status });
  return { barberId: p.barberId, status: p.status };
}

/** 统计：按项目 / 客人属性 / 时段(天) / 收入聚合。只统计已完成的单。 */
export async function aggregateStats(store, payload) {
  const p = payload || {};
  const all = await store.listOrders(p.barberId);
  const done = all.filter((o) => o.status === "completed" &&
    Number(o.actualEndTime || 0) >= Number(p.fromTs || 0) &&
    Number(o.actualEndTime || 0) <= Number(p.toTs || 0 || Number.MAX_SAFE_INTEGER));

  const byService = {}, byCustomerType = {}, byDay = {};
  let revenue = 0, totalDuration = 0;
  for (const o of done) {
    const dur = Math.max(0, Number(o.actualEndTime || 0) - Number(o.actualStartTime || 0));
    const price = Number(o.price || 0);
    revenue += price; totalDuration += dur;
    const s = byService[o.serviceName] = byService[o.serviceName] || { count: 0, totalDuration: 0 };
    s.count++; s.totalDuration += dur;
    byCustomerType[o.customerType] = (byCustomerType[o.customerType] || 0) + 1;
    const day = new Date(Number(o.actualEndTime || 0) + 8 * 3600e3).toISOString().slice(0, 10);
    byDay[day] = (byDay[day] || 0) + 1;
  }
  const avg = {};
  for (const [k, v] of Object.entries(byService)) avg[k] = Math.round(v.totalDuration / Math.max(1, v.count));
  return {
    completedCount: done.length,
    revenue,
    avgServiceMs: done.length ? Math.round(totalDuration / done.length) : 0,
    byService: avg, byServiceCount: Object.fromEntries(Object.entries(byService).map(([k, v]) => [k, v.count])),
    byCustomerType, byDay,
  };
}

/** 排队视图：给理发师端用（预付款同段优先、跨段不抢）。 */
export async function queueView(store, barberId, nowTs) {
  const orders = await store.listOrders(barberId);
  return sortQueue(activeOrders(orders), nowTs);
}
