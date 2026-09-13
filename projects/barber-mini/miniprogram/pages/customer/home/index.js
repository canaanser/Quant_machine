// 顾客端首页
//  ① 24h 时间轴（从现在到打烊，标出后面每一位：预约+排队合计）
//  ② 状态卡（忙不忙 / 等多久）
//  ③ 先选「我是谁 + 做什么」→ ④ 两个动作：立即排队（左·主）/ 提前预约（右）
import { watchBarber } from "../../../utils/watch.js";
import { api } from "../../../utils/cloud.js";
import { hhmm } from "../../../utils/time.js";

const TONE = { idle: "free", busy: "busy", rest: "rest" };
const TEXT = { idle: "空闲中", busy: "正在服务", rest: "休息中" };
const SUB = { idle: "现在到店可以直接安排", busy: "理发师手上还有一位，稍等一下", rest: "今天暂时不接单，可先预约" };
const FACE = { woman: "👩", man: "👨", elder: "🧓", child: "🧒" };

Page({
  data: {
    tone: "busy", statusText: "正在服务", statusSub: SUB.busy,
    waiting: 0, etaMin: 20, progress: 45, done: 0, updated: "--:--", mine: null,
    types: [
      { k: "woman", label: "女士", ico: "👩" }, { k: "man", label: "男士", ico: "👨" },
      { k: "elder", label: "老人", ico: "🧓" }, { k: "child", label: "小孩", ico: "🧒" },
    ],
    items: [
      { _id: "s1", name: "剪发", price: 38, min: 10, icon: "scissors" },
      { _id: "s2", name: "烫发", price: 288, min: 10, icon: "perm" },
      { _id: "s3", name: "染发", price: 258, min: 10, icon: "dye" },
      { _id: "s4", name: "护理", price: 128, min: 10, icon: "care" },
    ],
    pickedType: "man", pickedItem: "s1",
    nowText: "--:--", openTime: "09:00", closeTime: "21:00",
    segs: [], behindCount: 0, cntQueuing: 0, cntReserved: 0,
    sceneText: "",
  },
  onLoad() { this.refreshAll(); },
  onShow() { this.refreshAll(); },
  async refreshAll() {
    await this.buildTimeline();
    this.loadStats();
    try {
      const db = wx.cloud.database();
      if (!this.unwatch) this.unwatch = watchBarber(db, "b1", (b) => { if (b) this.applyBarber(b); });
    } catch (e) { /* 云未初始化 */ }
  },
  onUnload() { if (this.unwatch) this.unwatch(); },
  applyBarber(b) {
    this.setData({
      tone: TONE[b.status] || "rest", statusText: TEXT[b.status] || "休息中", statusSub: SUB[b.status] || "",
      progress: b.status === "busy" ? 55 : b.status === "idle" ? 12 : 100, updated: hhmm(Date.now()),
    });
  },
  // ★ 24h 时间轴：轴 = [开门, 打烊]；游标 = 现在；小人 = 后面每一位（预约+排队合计）
  async buildTimeline() {
    const now = Date.now();
    const day = new Date(); day.setHours(0, 0, 0, 0);
    const toTs = (s, fb) => {
      const m = /^(\d{1,2}):(\d{2})$/.exec(String(s || ""));
      return m ? day.getTime() + Number(m[1]) * 3600e3 + Number(m[2]) * 60e3 : day.getTime() + fb * 3600e3;
    };
    let open = toTs(this.data.openTime, 9), close = toTs(this.data.closeTime, 21);
    let openText = this.data.openTime, closeText = this.data.closeTime;
    try {
      const db = wx.cloud.database();
      const r = await db.collection("barbers").doc("b1").get();
      const bar = r.data || {};
      if (bar.openTime) { open = toTs(bar.openTime, 9); openText = bar.openTime; }
      if (bar.closeTime) { close = toTs(bar.closeTime, 21); closeText = bar.closeTime; }
    } catch (e) { /* 默认营业时间 */ }
    if (close <= now) close = now + 3600e3;
    const span = Math.max(1, close - open);
    const nowPct = Math.min(100, Math.max(0, ((now - open) / span) * 100));

    let list = [];
    try { const r = await api.queue({ barberId: "b1" }); list = r.list || []; } catch (e) { /* 未就绪 */ }
    const mine = list.find((o) => o.customerOpenid === "me" && o.status !== "serving");
    const ahead = mine ? list.findIndex((o) => o._id === mine._id) : list.filter((o) => o.status === "queuing").length;

    // 色条：正在服务(橙) 固定在最左；其后按顺序是排队(金) / 预约(蓝)
    const serving = list.find((o) => o.status === "serving");
    const rest = list.filter((o) => o.status !== "serving");
    const segs = [];
    if (serving) segs.push({ i: "s", k: "serving", w: 3, t: "正在" });
    rest.forEach((o, i) => segs.push({ i, k: o.status === "reserved" ? "reserved" : "queuing",
      w: o.status === "reserved" ? 2 : 2, t: o.status === "reserved" ? "约" : "排" }));
    const cntQueuing = list.filter((o) => o.status === "queuing").length;
    const cntReserved = list.filter((o) => o.status === "reserved").length;
    this.setData({
      nowText: hhmm(now), openTime: openText, closeTime: closeText,
      segs, behindCount: rest.length, cntQueuing, cntReserved,
      waiting: Math.max(0, ahead), etaMin: Math.max(0, ahead) * 10,
      mine: mine ? {
        tag: ["预付款", "已预约", "现场"][mine.priority] || "现场",
        serviceName: mine.serviceName, statusText: mine.status === "reserved" ? "已预约（未到点）" : "排队中",
        eta: mine.appointmentTime ? hhmm(mine.appointmentTime) : "等待叫号",
        progress: Math.min(100, Math.max(10, 100 - Math.max(0, ahead) * 15)),
      } : null,
      sceneText: "前面还有 " + Math.max(0, ahead) + " 位 · 我在队里等着",
    });
  },
  async loadStats() {
    try { const s = await api.stats({ barberId: "b1", fromTs: 0, toTs: 0 }); this.setData({ done: s.completedCount || 0 }); }
    catch (e) { /* 未就绪 */ }
  },
  pickType(e) { this.setData({ pickedType: e.currentTarget.dataset.k }); },
  goProgress() { wx.navigateTo({ url: "/pages/customer/progress/index" }); },
  pickItem(e) { this.setData({ pickedItem: e.currentTarget.dataset.id }); },
  goBook() { wx.navigateTo({ url: "/pages/customer/book/index?item=" + this.data.pickedItem + "&type=" + this.data.pickedType }); },
  // 立即排队：**秒开**（本地待提交单先带过去，云端后台建单）
  async joinQueue() {
    const app = getApp();
    app.globalData.lastOrder = { _id: "local_pending", customerOpenid: "me", customerName: "我",
      serviceItemId: this.data.pickedItem, serviceName: "排队中", priority: 2, status: "queuing", duration: 0 };
    app.globalData.pendingJoin = true;
    wx.navigateTo({ url: "/pages/customer/progress/index" });
    try {
      const r = await api.createOrder({ barberId: "b1", serviceItemId: this.data.pickedItem,
        customerType: this.data.pickedType, customerOpenid: "me", customerName: "我" });
      app.globalData.lastOrder = r && r.order;
      app.globalData.pendingJoin = false;
    } catch (e) {
      app.globalData.joinError = String((e && (e.errMsg || e.message)) || e).slice(0, 120);
      app.globalData.pendingJoin = false;
    }
  },
});
