// 极简版 V1 · 顾客端「看排队」——只保留老板截图上的模块：
// 状态大卡 + 三瓦片 + 立即预约/加入排队 + 服务项目列表。没有时间轴、没有场景图。
import { api } from "../../../utils/cloud.js";
import { hhmm } from "../../../utils/time.js";

const TONE = { idle: "free", busy: "busy", rest: "rest" };
const TEXT = { idle: "空闲中", busy: "正在服务", rest: "休息中" };
const SUB = { idle: "现在到店可以直接安排", busy: "理发师手上还有一位，稍等一下", rest: "今天暂时不接单，可先预约" };

Page({
  data: {
    tone: "busy", statusText: "正在服务", statusSub: SUB.busy, progress: 45,
    waiting: 0, etaMin: 20, done: 0, updated: "--:--",
    items: [
      { _id: "s1", name: "剪发", price: 38, min: 40, icon: "scissors", desc: "洗剪吹" },
      { _id: "s2", name: "烫发", price: 288, min: 150, icon: "perm", desc: "含造型" },
      { _id: "s3", name: "染发", price: 258, min: 120, icon: "dye", desc: "纯色" },
      { _id: "s4", name: "护理", price: 128, min: 60, icon: "care", desc: "头皮护理" },
    ],
  },
  onShow() { this.load(); },
  async load() {
    try {
      const db = wx.cloud.database();
      const b = await db.collection("barbers").doc("b1").get();
      const bar = b.data || {};
      this.setData({ tone: TONE[bar.status] || "rest", statusText: TEXT[bar.status] || "休息中",
        statusSub: SUB[bar.status] || "", progress: bar.status === "busy" ? 55 : bar.status === "idle" ? 12 : 100,
        updated: hhmm(Date.now()) });
    } catch (e) {}
    try {
      const [q, s] = await Promise.all([api.queue({ barberId: "b1" }), api.stats({ barberId: "b1", fromTs: 0, toTs: 0 })]);
      const list = q.list || [];
      const ahead = list.filter((o) => o.status === "queuing").length;
      this.setData({ waiting: ahead, etaMin: ahead * 20, done: s.completedCount || 0, updated: hhmm(Date.now()) });
    } catch (e) {}
  },
  goBook() { wx.switchTab({ url: "/pages/customer/home/index" }); },
  async joinQueue() {
    wx.showLoading({ title: "正在排队…", mask: true });
    try { await api.createOrder({ barberId: "b1", serviceItemId: "s1", customerType: "man", customerOpenid: "me", customerName: "我" }); }
    catch (e) {}
    finally { wx.hideLoading(); }
    this.load();
    wx.showToast({ title: "已加入排队", icon: "success" });
  },
});
