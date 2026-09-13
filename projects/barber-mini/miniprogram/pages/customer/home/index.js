// 顾客端首页：先出内容（mock 兜底），云环境就绪后用 watch 覆盖 → 永不白屏。
import { watchBarber } from "../../../utils/watch.js";
import { api } from "../../../utils/cloud.js";

const TONE = { idle: "free", busy: "busy", rest: "rest" };
const TEXT = { idle: "空闲中", busy: "正在服务", rest: "休息中" };
const SUB = { idle: "现在到店可以直接安排", busy: "理发师手上还有一位，稍等一下", rest: "今天暂时不接单，可先预约" };
const STATUS_TEXT = { reserved: "已预约", queuing: "排队中", serving: "正在服务", completed: "已完成", cancelled: "已取消" };

Page({
  data: {
    tone: "busy", statusText: "正在服务", statusSub: SUB.busy,
    waiting: 2, etaMin: 20, progress: 45, done: 6, updated: "--:--", mine: null,
    faces: ["王", "李", "张"],
    slots: [],
    items: [
      { _id: "s1", name: "剪发", price: 38, duration: 40, icon: "scissors", desc: "洗剪吹" },
      { _id: "s2", name: "烫发", price: 288, duration: 150, icon: "perm", desc: "含造型" },
      { _id: "s3", name: "染发", price: 258, duration: 120, icon: "dye", desc: "纯色" },
      { _id: "s4", name: "护理", price: 128, duration: 60, icon: "care", desc: "头皮护理" },
    ],
  },
  onLoad() {
    this.setData({ updated: new Date().toTimeString().slice(0, 5) });
    this.buildSlots();
    this.loadStats();
    try {
      const db = wx.cloud.database();
      this.unwatch = watchBarber(db, "b1", (b) => { if (b) this.applyBarber(b); });
    } catch (e) { /* 云未初始化：留 mock */ }
  },
  buildSlots() {
    const base = new Date(); base.setMinutes(0, 0, 0);
    const slots = [];
    for (let i = 1; i <= 6; i++) {
      const ts = base.getTime() + i * 40 * 60000;
      slots.push({ ts, label: new Date(ts).toTimeString().slice(0, 5), busy: false, state: i === 1 ? "now" : "free" });
    }
    this.setData({ slots });
  },
  onUnload() { if (this.unwatch) this.unwatch(); },
  applyBarber(b) {
    this.setData({
      tone: TONE[b.status] || "rest",
      statusText: TEXT[b.status] || "休息中",
      statusSub: SUB[b.status] || "",
      progress: b.status === "busy" ? 55 : b.status === "idle" ? 12 : 100,
      updated: new Date().toTimeString().slice(0, 5),
    });
  },
  async loadStats() {
    try {
      const s = await api.stats({ barberId: "b1", fromTs: 0, toTs: 0 });
      this.setData({ done: s.completedCount || 0 });
    } catch (e) { /* 云端还没数据：用默认值 */ }
  },
  goBook() { wx.navigateTo({ url: "/pages/customer/book/index" }); },
  async joinQueue() {
    // ★ 先给反馈再等网络：云函数一次往返约 1 秒（实测 0.8–1.1s），不给提示就像卡死
    wx.showLoading({ title: "正在排队…", mask: true });
    try {
      const r = await api.createOrder({ barberId: "b1", serviceItemId: "s1", customerOpenid: "me", customerName: "我", customerType: "man" });
      getApp().globalData.lastOrder = r && r.order;      // 把结果直接带去进度页，省掉一次查询
      this.setData({ waiting: (this.data.waiting || 0) + 1 });
    } catch (e) {
      wx.showModal({ title: "排队失败", content: String((e && (e.errMsg || e.message)) || e).slice(0, 100), showCancel: false });
    } finally { wx.hideLoading(); }
    wx.navigateTo({ url: "/pages/customer/progress/index" });
  },
});
