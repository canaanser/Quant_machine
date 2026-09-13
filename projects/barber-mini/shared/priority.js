// 优先级与排队排序 —— **唯一真源**。
// 规则（老板默认值）：0=预付款、1=已预约、2=现场；**预付款只在同一时间段内优先**，不跨段抢。
export const PRIORITY = { PREPAID: 0, RESERVED: 1, WALKIN: 2 };

const HOUR = 60 * 60 * 1000;

/**
 * 时间段桶（小时粒度）：
 *   · 有预约 → 按预约时刻分桶；
 *   · **现场单（无预约）→ 算"当前时段"**（人就在店里；这样它才和"本时段的预约单"可比优先级）。
 * 跨桶按时段先后 → **预付款不许跨段插队**。
 */
export function slotBucket(order, nowTs) {
  const t = Number((order && order.appointmentTime) || 0);
  if (t > 0) return Math.floor(t / HOUR);
  return Math.floor(Number(nowTs || Date.now()) / HOUR);
}

/** 优先级：**以订单上的 priority 为准**（真源），缺省时用 isPrepaid/appointmentTime 推。 */
export function normalizePriority(order) {
  const o = order || {};
  if (o.priority !== undefined && o.priority !== null) return Number(o.priority);
  if (o.isPrepaid) return PRIORITY.PREPAID;
  return Number(o.appointmentTime || 0) > 0 ? PRIORITY.RESERVED : PRIORITY.WALKIN;
}

/**
 * 排队比较器（升序 = 先服务）：
 *  ① 不同时段 → **按时段先后**（预付款也不许跨段插队）；
 *  ② 同时段（或都是现场单）→ 优先级升序；
 *  ③ 仍相同 → 预约时间 / 创建时间升序（先到先得）。
 */
export function compareOrders(a, b, nowTs) {
  const ba = slotBucket(a, nowTs), bb = slotBucket(b, nowTs);
  if (ba !== null && bb !== null && ba !== bb) return ba - bb;
  const pa = normalizePriority(a), pb = normalizePriority(b);
  if (pa !== pb) return pa - pb;
  // ★ "先到先得"看的是**下单时刻**（createdAt），不是预约时刻——
  //   同一时段里两个人的预约时刻本来就一样，拿它当 tiebreak 会退化成"输入顺序"（实测被单测抓红）。
  const ca = Number(a.createdAt || 0), cb = Number(b.createdAt || 0);
  if (ca !== cb) return ca - cb;
  const ta = Number(a.appointmentTime || 0), tb = Number(b.appointmentTime || 0);
  if (ta !== tb) return ta - tb;
  return String(a._id || "").localeCompare(String(b._id || ""));   // 最后兜底：确定性，不靠排序实现
}

export function sortQueue(orders, nowTs) {
  return [...(orders || [])].sort((a, b) => compareOrders(a, b, nowTs));
}

/** 真正"在排队/在服务"的单才参与排序。 */
export function activeOrders(orders) {
  return (orders || []).filter((o) => ["reserved", "queuing", "serving"].includes(o.status));
}
