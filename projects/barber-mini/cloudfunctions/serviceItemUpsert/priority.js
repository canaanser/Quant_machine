// 优先级与排队排序 —— **唯一真源**（CommonJS）
const PRIORITY = { PREPAID: 0, RESERVED: 1, WALKIN: 2 };
const HOUR = 60 * 60 * 1000;

/** 时段分桶：有预约按预约时刻；现场单算「当前时段」（这样才和本时段预约单可比优先级）。 */
function slotBucket(order, nowTs) {
  const t = Number((order && order.appointmentTime) || 0);
  if (t > 0) return Math.floor(t / HOUR);
  return Math.floor(Number(nowTs || Date.now()) / HOUR);
}

function normalizePriority(order) {
  const o = order || {};
  if (o.priority !== undefined && o.priority !== null) return Number(o.priority);
  if (o.isPrepaid) return PRIORITY.PREPAID;
  return Number(o.appointmentTime || 0) > 0 ? PRIORITY.RESERVED : PRIORITY.WALKIN;
}

/** 升序 = 先服务：① 跨时段按时段先后（预付款也不许跨段插队）② 同段按优先级 ③ 先到先得（下单时刻） */
function compareOrders(a, b, nowTs) {
  const ba = slotBucket(a, nowTs), bb = slotBucket(b, nowTs);
  if (ba !== bb) return ba - bb;
  const pa = normalizePriority(a), pb = normalizePriority(b);
  if (pa !== pb) return pa - pb;
  const ca = Number(a.createdAt || 0), cb = Number(b.createdAt || 0);
  if (ca !== cb) return ca - cb;
  return String(a._id || "").localeCompare(String(b._id || ""));
}

function sortQueue(orders, nowTs) { return [...(orders || [])].sort((a, b) => compareOrders(a, b, nowTs)); }
const activeOrders = (orders) => (orders || []).filter((o) => ["reserved", "queuing", "serving"].includes(o.status));

module.exports = { PRIORITY, slotBucket, normalizePriority, compareOrders, sortQueue, activeOrders };
