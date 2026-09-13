// 数据看板：主卡（大数字+周期/眼睛小按钮）→ 今日目标 → 忙闲时段 → 排行榜 → 客人明细(折叠/透视) → 更多(折叠)
import { api } from "../../../utils/cloud.js";

const RANGES = [
  { k: "today", l: "今天" }, { k: "week", l: "本周" }, { k: "month", l: "本月" },
  { k: "lastMonth", l: "上月" }, { k: "year", l: "今年" }, { k: "lastYear", l: "去年" }, { k: "all", l: "全部" },
];
const SORTS = [{ k: "revenue", l: "消费" }, { k: "count", l: "次数" }, { k: "ms", l: "时长" }];
const TYPE_LABEL = { woman: "女士", man: "男士", elder: "老人", child: "小孩" };

Page({
  data: {
    theme: getApp().themeClass(),
    ranges: RANGES, sorts: SORTS, range: "today", rangeLabel: "今天", sort: "revenue",
    b: { summary: { count: 0, revenue: 0, perCustomer: 0, people: 0, customers: 0, avgMs: 0 } },
    avgMinText: "0 分", rank: [], customers: [], byService: [], byType: [], byHour: [], byDay: [],
    hideMoney: false, showCustomers: false, showMore: false, openKey: "",
    goal: 300, goalPct: 0, goalLeft: 300,
    openHour: 9, closeHour: 21,
  },
  onShow() { this.load(); },
  async load() {
    try {
      const b = await api.board({ barberId: "b1", range: this.data.range });
      const goal = await this.loadGoal();
      await this.loadHours();
      const barMax = Math.max(1, ...b.byService.map((x) => x.count));
      const hourMax = Math.max(1, ...b.byHour.map((x) => x.count));
      const am = Math.round((b.summary.avgMs || 0) / 60000);
      const typeCount = {}; // 每个客人的项目分布（透视图用）
      this.setData({
        b, goal,
        avgMinText: am < 1 ? "<1 分" : am + " 分",
        goalPct: Math.min(100, Math.round(((b.summary.revenue || 0) / Math.max(1, goal)) * 100)),
        goalLeft: Math.max(0, goal - (b.summary.revenue || 0)),
        byService: b.byService.map((x) => ({ ...x, pct: Math.round((x.count / barMax) * 100), avgMin: Math.round(x.ms / Math.max(1, x.count) / 60000) })),
        byType: b.byType.map((x) => ({ ...x, label: TYPE_LABEL[x.type] || x.type })),
        // ★ 时段柱状**铺满营业时间**（空时段也留柱子），看起来才像"今天有多忙"
        byHour: this.fillHours(b.byHour, hourMax),
        byDay: b.byDay.slice(-14).reverse(),
      });
      this.applySort();
    } catch (e) {
      wx.showModal({ title: "看板读取失败", content: String((e && (e.errMsg || e.message)) || e).slice(0, 110), showCancel: false });
    }
  },
  async loadGoal() {
    try {
      const db = wx.cloud.database();
      const r = await db.collection("barbers").doc("b1").get();
      return Number((r.data || {}).dailyGoal || 0) || 300;
    } catch (e) { return 300; }
  },
  async loadHours() {
    try {
      const db = wx.cloud.database();
      const r = await db.collection("barbers").doc("b1").get();
      const bar = r.data || {};
      const toH = (s, fb) => { const m = /^(\d{1,2}):/.exec(String(s || "")); return m ? Number(m[1]) : fb; };
      this.setData({ openHour: toH(bar.openTime, 9), closeHour: toH(bar.closeTime, 21) });
    } catch (e) { this.setData({ openHour: 9, closeHour: 21 }); }
  },
  /** 把营业时段每一小时都补出来（没单的小时高度=最小），柱子才连成"一整天的形状" */
  fillHours(hours, hourMax) {
    const map = {};
    (hours || []).forEach((x) => { map[x.hour] = x.count; });
    const out = [];
    for (let h = this.data.openHour; h <= this.data.closeHour; h++) {
      const c = map[h] || 0;
      out.push({ hour: h, count: c, h: Math.round((c / hourMax) * 150) + (c ? 14 : 6) });
    }
    return out;
  },
  applySort() {
    const b = this.data.b; const key = this.data.sort;
    const list = [...(b.customers || [])].sort((x, y) =>
      key === "ms" ? y.ms - x.ms : key === "count" ? y.count - x.count : y.revenue - x.revenue);
    this.setData({
      customers: list.map((c) => {
        const parts = c.byService || [];
        const max = Math.max(1, ...parts.map((p) => p.revenue || 0));
        return { ...c, min: Math.round(c.ms / 60000), avgMin: Math.round((c.avgMs || 0) / 60000),
          byService: parts.map((p) => ({ ...p, pct: Math.round(((p.revenue || 0) / max) * 100) })) };
      }),
      rank: list.slice(0, 5).map((c) => ({ ...c, min: Math.round(c.ms / 60000), avgMin: Math.round((c.avgMs || 0) / 60000) })),
    });
  },
  pickRange() {
    wx.showActionSheet({
      itemList: RANGES.map((r) => r.l),
      success: (res) => {
        const r = RANGES[res.tapIndex];
        this.setData({ range: r.k, rangeLabel: r.l }, () => this.load());
      },
    });
  },
  pickSort(e) { this.setData({ sort: e.currentTarget.dataset.k }, () => this.applySort()); },
  toggleEye() { this.setData({ hideMoney: !this.data.hideMoney }); },
  toggleCustomers() { this.setData({ showCustomers: !this.data.showCustomers }); },
  toggleMore() { this.setData({ showMore: !this.data.showMore }); },
  openCustomer(e) { const k = e.currentTarget.dataset.k; this.setData({ openKey: this.data.openKey === k ? "" : k, showCustomers: true }); },
  setGoal() {
    wx.showModal({ title: "今日目标（元）", editable: true, placeholderText: String(this.data.goal),
      success: async (r) => {
        if (!r.confirm || !r.content) return;
        const g = Math.max(0, Number(r.content) || 0);
        try { await api.saveSettings({ barberId: "b1", dailyGoal: g }); this.setData({ goal: g }); this.load(); }
        catch (e) { wx.showToast({ title: "保存失败", icon: "none" }); }
      } });
  },
});
