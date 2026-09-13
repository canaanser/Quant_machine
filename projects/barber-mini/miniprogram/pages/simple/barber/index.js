// 极简版 V1 · 经营者端「工作台」——只保留截图上的模块：
// 头像+名字+状态 + 三瓦片 + 当前服务卡 + 接单状态 + 快捷接单。
import { api } from "../../../utils/cloud.js";

const TONE = { idle: "free", busy: "busy", rest: "rest" };
const TEXT = { idle: "空闲", busy: "服务中", rest: "休息" };

Page({
  data: {
    status: "idle", tone: "free", statusText: "空闲",
    today: 0, revenue: 0, avgMin: 0, elapsed: 0, currentName: "暂无客人", currentItem: "—",
    servingId: null, picked: null, itemPicked: null, clickCount: 0,
    types: [
      { k: "woman", label: "女士", ico: "👩" }, { k: "man", label: "男士", ico: "👨" },
      { k: "elder", label: "老人", ico: "🧓" }, { k: "child", label: "小孩", ico: "🧒" },
    ],
    items: [
      { _id: "s1", name: "剪发", price: 38, defaultDuration: 2400000 }, { _id: "s2", name: "烫发", price: 288, defaultDuration: 9000000 },
      { _id: "s3", name: "染发", price: 258, defaultDuration: 7200000 },
    ],
    showBoard: false,
    b: { summary: { count: 0, revenue: 0, perCustomer: 0 } }, rank: [], customers: [], byService: [],
  },
  onShow() { this.load(); this.timer = setInterval(() => this.tick(), 30000); },
  onHide() { clearInterval(this.timer); },
  onUnload() { clearInterval(this.timer); },
  async load() {
    try {
      const [s, q] = await Promise.all([api.stats({ barberId: "b1", fromTs: 0, toTs: 0 }), api.queue({ barberId: "b1" })]);
      const sv = q.serving;
      this.setData({
        today: s.completedCount || 0, revenue: s.revenue || 0, avgMin: Math.round((s.avgServiceMs || 0) / 60000),
        servingId: sv ? sv._id : null, currentName: sv ? (sv.customerName || "顾客") : "暂无客人",
        currentItem: sv ? sv.serviceName : "—",
        elapsed: sv ? Math.floor((Date.now() - Number(sv.actualStartTime || Date.now())) / 60000) : 0,
      });
      if (sv) this.apply("busy");
    } catch (e) {}
  },
  tick() {
    if (!this.data.servingId) return;
    this.setData({ elapsed: this.data.elapsed + 1 });
  },
  pickType(e) { this.setData({ picked: e.currentTarget.dataset.k, clickCount: this.data.clickCount + 1 }); },
  pickItem(e) { this.setData({ itemPicked: e.currentTarget.dataset.id, clickCount: this.data.clickCount + 1 }); },
  async start() {
    const { picked, itemPicked } = this.data;
    if (!picked || !itemPicked) return wx.showToast({ title: "先点客人类型，再点项目", icon: "none" });
    try {
      const r = await api.createOrder({ barberId: "b1", serviceItemId: itemPicked, customerType: picked,
        customerOpenid: "walk_" + Date.now(), customerName: "现场客" });
      await api.transition({ orderId: r.order._id, to: "serving" });
      this.setData({ picked: null, itemPicked: null, clickCount: 0 });
      this.apply("busy"); this.load();
    } catch (e) { wx.showToast({ title: "接单失败", icon: "none" }); }
  },
  async finish() {
    if (!this.data.servingId) return wx.showToast({ title: "当前没有在服务的单", icon: "none" });
    try { await api.transition({ orderId: this.data.servingId, to: "completed" }); this.apply("idle"); this.load(); wx.showToast({ title: "本单完成", icon: "success" }); }
    catch (e) { wx.showToast({ title: "完成失败", icon: "none" }); }
  },
  async setStatus(e) {
    const s = e.currentTarget.dataset.s;
    try { await api.setBarberStatus({ barberId: "b1", status: s }); this.apply(s); }
    catch (err) { wx.showToast({ title: "切不了", icon: "none" }); }
  },
  apply(s) { this.setData({ status: s, tone: TONE[s], statusText: TEXT[s] }); },
  // 看板（折叠展开时才拉数据，省流量）
  async toggleBoard() {
    const on = !this.data.showBoard;
    this.setData({ showBoard: on });
    if (!on) return;
    try {
      const b = await api.board({ barberId: "b1", range: "today" });
      this.setData({
        b,
        rank: (b.top || []).map((c) => ({ ...c, min: Math.round(c.ms / 60000) })),
        customers: (b.customers || []).slice(0, 10).map((c) => ({ ...c, min: Math.round(c.ms / 60000), avgMin: Math.round((c.avgMs || 0) / 60000) })),
        byService: (b.byService || []).map((x) => ({ ...x, avgMin: Math.round(x.ms / Math.max(1, x.count) / 60000) })),
      });
    } catch (e) { wx.showToast({ title: "看板数据读不到", icon: "none" }); }
  },
});
