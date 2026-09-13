import { api } from "../../../utils/cloud.js";

const COLOR = ["#C9A227", "#17B26A", "#8FB4FF", "#E5484D"];
const LABEL = { woman: "女士", man: "男士", elder: "老人", child: "小孩" };

Page({
  data: {
    s: { completedCount: 0, revenue: 0, avgServiceMs: 0, byServiceCount: {}, byService: {}, byCustomerType: {} },
    revenueYuan: 0, avgMin: 0, bars: [], types: [], days: [],
  },
  onLoad() { this.load(); },
  async load() {
    let s = null;
    try { s = await api.stats({ barberId: "b1", fromTs: 0, toTs: 0 }); } catch (e) { /* 云端未就绪 */ }
    if (!s || !s.completedCount) s = this.demo();      // 没数据时用示例，界面不空
    this.setData({
      s,
      revenueYuan: s.revenue,
      avgMin: Math.round((s.avgServiceMs || 0) / 60000),
      bars: this.toBars(s),
      types: this.toTypes(s),
      days: this.toDays(s),
    });
  },
  demo() {
    return {
      completedCount: 12, revenue: 1680, avgServiceMs: 52 * 60000,
      byServiceCount: { 剪发: 6, 烫发: 3, 染发: 2, 护理: 1 },
      byService: { 剪发: 38 * 60000, 烫发: 140 * 60000, 染发: 110 * 60000, 护理: 55 * 60000 },
      byCustomerType: { woman: 6, man: 3, elder: 2, child: 1 },
      byDay: { "周一": 1, "周二": 2, "周三": 1, "周四": 3, "周五": 2, "周六": 2, "周日": 1 },
    };
  },
  toBars(s) {
    const counts = s.byServiceCount || {};
    const max = Math.max(1, ...Object.values(counts));
    return Object.entries(counts).map(([name, count]) => ({
      name, count,
      pct: Math.round((count / max) * 100),
      avgMin: Math.round(((s.byService || {})[name] || 0) / 60000),
    }));
  },
  toTypes(s) {
    const m = s.byCustomerType || {};
    const total = Math.max(1, Object.values(m).reduce((a, b) => a + b, 0));
    return Object.entries(m).map(([k, count], i) => ({
      k, label: LABEL[k] || k, count, color: COLOR[i % COLOR.length],
      pct: Math.round((count / total) * 100),
    }));
  },
  toDays(s) {
    const m = s.byDay || {};
    const keys = Object.keys(m);
    if (!keys.length) return [];
    const max = Math.max(1, ...Object.values(m));
    return keys.map((d) => ({ d: String(d).slice(-2), h: Math.round((m[d] / max) * 170) + 12 }));
  },
});
