// 数据看板聚合（服务端一份）：支持时间范围筛选、客户维度、消费排行、时段/项目分布。
// 规则：**没名字的客人统一归到「其他客人」**（老板 2026-09-14 明确）。
const ANON = "其他客人";
const DAY = 24 * 3600 * 1000;

function rangeToTs(range, now) {
  const d = new Date(now + 8 * 3600e3);          // 按北京时间取当日边界
  const y = d.getUTCFullYear(), m = d.getUTCMonth(), day = d.getUTCDate();
  const dayStart = Date.UTC(y, m, day) - 8 * 3600e3;
  if (range === "today") return { from: dayStart, to: dayStart + DAY };
  if (range === "week") {
    const wd = (d.getUTCDay() + 6) % 7;           // 周一为一周起点
    return { from: dayStart - wd * DAY, to: dayStart + (7 - wd) * DAY };
  }
  if (range === "month") return { from: Date.UTC(y, m, 1) - 8 * 3600e3, to: Date.UTC(y, m + 1, 1) - 8 * 3600e3 };
  return { from: 0, to: Number.MAX_SAFE_INTEGER };
}

exports.main = async (event) => {
  const wxServer = require("wx-server-sdk");
  wxServer.init();
  const db = wxServer.database();
  const barberId = (event && event.barberId) || "b1";
  const now = Date.now();
  const { from, to } = rangeToTs((event && event.range) || "today", now);

  // 拉取该理发师已完成的单（默认最多 500 条；超过请加索引/分页）
  const r = await db.collection("orders")
    .where({ barberId, status: "completed" })
    .orderBy("actualEndTime", "desc").limit(500).get();
  const all = r.data || [];
  const done = all.filter((o) => {
    const t = Number(o.actualEndTime || 0);
    return t >= from && t < to;
  });

  const byService = {}, byType = {}, byDay = {}, byHour = {}, cust = {};
  let revenue = 0, totalMs = 0;
  const uniq = new Set();

  for (const o of done) {
    const ms = Math.max(0, Number(o.actualEndTime || 0) - Number(o.actualStartTime || 0));
    const price = Number(o.price || 0);
    revenue += price; totalMs += ms;

    const svc = byService[o.serviceName] = byService[o.serviceName] || { name: o.serviceName, count: 0, revenue: 0, ms: 0 };
    svc.count++; svc.revenue += price; svc.ms += ms;

    const ty = o.customerType || "man";
    byType[ty] = byType[ty] || { type: ty, count: 0, revenue: 0 };
    byType[ty].count++; byType[ty].revenue += price;

    const endTs = Number(o.actualEndTime || 0);
    const dayKey = new Date(endTs + 8 * 3600e3).toISOString().slice(5, 10);
    byDay[dayKey] = byDay[dayKey] || { day: dayKey, count: 0, revenue: 0 };
    byDay[dayKey].count++; byDay[dayKey].revenue += price;

    const hour = new Date(endTs + 8 * 3600e3).getUTCHours();
    byHour[hour] = (byHour[hour] || 0) + 1;

    // ★ 没名字（或占位的"顾客/我"）→ 归到「其他客人」
    const rawName = String(o.customerName || "").trim();
    const anon = !rawName || ["顾客", "我", "探针", "现场客", "滚动测试"].includes(rawName);
    const key = anon ? ANON : rawName;
    const c = cust[key] = cust[key] || { key, name: key, count: 0, revenue: 0, ms: 0, lastAt: 0, anon };
    c.count++; c.revenue += price; c.ms += ms;
    if (endTs > c.lastAt) c.lastAt = endTs;
    if (!anon) uniq.add(key);
  }

  const customers = Object.values(cust).map((c) => ({
    ...c, avgMs: c.count ? Math.round(c.ms / c.count) : 0, min: Math.round(c.ms / 60000),
    lastText: c.lastAt ? new Date(c.lastAt + 8 * 3600e3).toISOString().slice(5, 16).replace("T", " ") : "",
  }));
  const top = [...customers].sort((a, b) => b.revenue - a.revenue).slice(0, 5);
  const topByCount = [...customers].sort((a, b) => b.count - a.count).slice(0, 5);
  const topByTime = [...customers].sort((a, b) => b.ms - a.ms).slice(0, 5);

  return {
    range: (event && event.range) || "today",
    from, to,
    summary: {
      count: done.length, revenue, avgMs: done.length ? Math.round(totalMs / done.length) : 0,
      customers: uniq.size, perCustomer: done.length ? Math.round(revenue / done.length) : 0,
      people: done.length,                      // 服务人次
    },
    byService: Object.values(byService).sort((a, b) => b.count - a.count),
    byType: Object.values(byType).sort((a, b) => b.count - a.count),
    byDay: Object.values(byDay).sort((a, b) => a.day.localeCompare(b.day)),
    byHour: Object.entries(byHour).map(([h, n]) => ({ hour: Number(h), count: n })).sort((a, b) => a.hour - b.hour),
    customers: customers.sort((a, b) => b.revenue - a.revenue),
    top, topByCount, topByTime,
  };
};
