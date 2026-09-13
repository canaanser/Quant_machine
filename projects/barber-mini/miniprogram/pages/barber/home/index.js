// 经营者工作台：看板瓦片 + 当前服务 + 一键状态 + 快捷接单（≤3 击）+ 排队列表
import { api } from "../../../utils/cloud.js";
import { priorityLabel } from "../../../utils/cloud.js";

const TONE = { idle: "free", busy: "busy", rest: "rest" };
const TEXT = { idle: "空闲", busy: "服务中", rest: "休息" };
const STATUS_TEXT = { reserved: "已预约", queuing: "排队中", serving: "服务中" };
const TAG_CLASS = { 0: "pill--gold", 1: "pill--busy", 2: "" };

Page({
  data: {
    status: "idle", tone: "free", statusText: "空闲",
    today: 0, revenue: 0, avgMin: 0, elapsed: 0,
    currentName: "暂无客人", currentItem: "—",
    picked: null, itemPicked: null, clickCount: 0, queue: [],
    types: [
      { k: "woman", label: "女士", ico: "👩" }, { k: "man", label: "男士", ico: "👨" },
      { k: "elder", label: "老人", ico: "🧓" }, { k: "child", label: "小孩", ico: "🧒" },
    ],
    items: [
      { _id: "s1", name: "剪发", price: 38 }, { _id: "s2", name: "烫发", price: 288 },
      { _id: "s3", name: "染发", price: 258 },
    ],
  },
  onShow() { this.refresh(); },
  async refresh() {
    try {
      const [s, q] = await Promise.all([
        api.stats({ barberId: "b1", fromTs: 0, toTs: 0 }),
        api.queue({ barberId: "b1" }),
      ]);
      const list = (q.list || []).map((o) => ({
        _id: o._id, name: o.customerName || "顾客", serviceName: o.serviceName,
        statusText: STATUS_TEXT[o.status] || o.status, status: o.status,
        tag: priorityLabel(o.priority), tagClass: TAG_CLASS[o.priority] || "",
      }));
      this.setData({
        today: s.completedCount || 0, revenue: s.revenue || 0, avgMin: Math.round((s.avgServiceMs || 0) / 60000),
        queue: list,
        currentName: q.serving ? (q.serving.customerName || "顾客") : "暂无客人",
        currentItem: q.serving ? q.serving.serviceName : "—",
        servingId: q.serving ? q.serving._id : null,
      });
      if (q.serving) this.applyStatus("busy");
    } catch (e) { /* 云端未就绪：保持占位，界面不空 */ }
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
      this.setData({ clickCount: this.data.clickCount + 1, picked: null, itemPicked: null });
      this.applyStatus("busy");
      wx.showToast({ title: "已开始服务", icon: "success" });
    } catch (e) { wx.showToast({ title: "云端未就绪", icon: "none" }); }
  },
  async finish() {
    try {
      const id = this.data.servingId || ((this.data.queue || []).find((o) => o.status === "serving") || {})._id;
      if (!id) return wx.showToast({ title: "当前没有在服务的单", icon: "none" });
      await api.transition({ orderId: id, to: "completed" });
      this.setData({ servingId: null });
      this.applyStatus("idle");
      await this.refresh();
      wx.showToast({ title: "本单完成", icon: "success" });
    } catch (e) { wx.showToast({ title: "完成失败：" + String(e.errMsg || e).slice(0, 18), icon: "none" }); }
  },
  async setStatus(e) {
    const s = e.currentTarget.dataset.s;
    this.applyStatus(s);
    try { await api.setBarberStatus({ barberId: "b1", status: s }); }
    catch (err) { wx.showToast({ title: "云端未就绪", icon: "none" }); }
  },
  applyStatus(s) { this.setData({ status: s, tone: TONE[s], statusText: TEXT[s] }); },
});
