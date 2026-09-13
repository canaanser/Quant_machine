// 经营者工作台 —— **只放"此刻要干的活"**：当前服务 / 一键状态 / 快捷接单 / 排队（前三位）+ 四个入口。
// 经营与配置类（数据看板 / 流水 / 目标 / 营业时间 / 项目 / 调试）都在各自页面，不再堆这一页。
import { api, priorityLabel } from "../../../utils/cloud.js";

const TONE = { idle: "free", busy: "busy", rest: "rest" };
const TEXT = { idle: "空闲", busy: "服务中", rest: "休息" };
const STATUS_TEXT = { reserved: "已预约", queuing: "排队中", serving: "服务中" };
const TAG_CLASS = { 0: "pill--gold", 1: "pill--busy", 2: "" };
// 物化头像：男女老少小孩一眼分得清（老板 2026-09-14：「用物化的头像告诉我男女老少」）
const FACE = { woman: "👩", man: "👨", elder: "🧓", child: "🧒" };
const TYPE_TEXT = { woman: "女士", man: "男士", elder: "老人", child: "小孩" };

Page({
  data: {
    status: "idle", tone: "free", statusText: "空闲",
    currentName: "暂无客人", currentItem: "—", elapsed: 0, overtime: 0,
    servingId: null, servingStartAt: 0, servingPlanMin: 0,
    picked: null, itemPicked: null, clickCount: 0,
    queue: [], queueTop: [], autoFlow: false,
    page: 0, currentFace: "🧑", currentTypeText: "", currentTag: "",
    types: [
      { k: "woman", label: "女士", ico: "👩" }, { k: "man", label: "男士", ico: "👨" },
      { k: "elder", label: "老人", ico: "🧓" }, { k: "child", label: "小孩", ico: "🧒" },
    ],
    items: [
      { _id: "s1", name: "剪发", price: 38 }, { _id: "s2", name: "烫发", price: 288 }, { _id: "s3", name: "染发", price: 258 },
    ],
  },
  onShow() {
    this.setData({ autoFlow: !!(getApp().globalData || {}).autoFlow });
    this.refresh();
    this.startTick();
  },
  onHide() { this.stopTick(); },
  onUnload() { this.stopTick(); },
  startTick() { this.stopTick(); this._t = setInterval(() => this.tickElapsed(), 1000); this.tickElapsed(); },
  stopTick() { if (this._t) { clearInterval(this._t); this._t = null; } },
  // ★ 只提示、不代劳：时长是预估，必须理发师点「完成本单」
  tickElapsed() {
    const st = Number(this.data.servingStartAt || 0);
    if (!st) { if (this.data.elapsed !== 0) this.setData({ elapsed: 0, overtime: 0 }); return; }
    const min = Math.floor((Date.now() - st) / 60000);
    const ot = Math.max(0, min - Number(this.data.servingPlanMin || 0));
    if (min !== this.data.elapsed || ot !== this.data.overtime) this.setData({ elapsed: min, overtime: ot });
  },
  async refresh() {
    try {
      const q = await api.queue({ barberId: "b1" });
      const list = (q.list || []).map((o) => ({
        _id: o._id, name: o.customerName || "顾客", serviceName: o.serviceName,
        statusText: STATUS_TEXT[o.status] || o.status, status: o.status,
        tag: priorityLabel(o.priority), tagClass: TAG_CLASS[o.priority] || "",
        face: FACE[o.customerType] || "🧑", faceKey: o.customerType || "man",
      }));
      const sv = q.serving || null;
      this.setData({
        queue: list, queueTop: list.slice(0, 3),
        currentName: sv ? (sv.customerName || "顾客") : "现在没有人",
        currentItem: sv ? sv.serviceName : "点右边一屏接单",
        currentFace: sv ? (FACE[sv.customerType] || "🧑") : "🪑",
        currentTypeText: sv ? (TYPE_TEXT[sv.customerType] || "") : "",
        currentTag: sv ? priorityLabel(sv.priority) : "",
        servingId: sv ? sv._id : null,
        servingStartAt: sv ? Number(sv.actualStartTime || 0) : 0,
        servingPlanMin: sv ? Math.round(Number(sv.duration || 0) / 60000) : 0,
      });
      if (q.serving) this.applyStatus("busy"); else if (this.data.status === "busy") this.applyStatus("idle");
    } catch (e) { /* 云端未就绪：保持占位 */ }
  },
  pickType(e) { this.setData({ picked: e.currentTarget.dataset.k, clickCount: this.data.clickCount + 1 }); },
  onSwipe(e) { this.setData({ page: e.detail.current }); },
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
      await this.refresh();
      wx.showToast({ title: "已开始服务", icon: "success" });
    } catch (e) { wx.showModal({ title: "接单失败", content: String((e && (e.errMsg || e.message)) || e).slice(0, 110), showCancel: false }); }
  },
  async finish() {
    const id = this.data.servingId;
    if (!id) return wx.showToast({ title: "当前没有在服务的单", icon: "none" });
    try {
      await api.transition({ orderId: id, to: "completed" });
      this.applyStatus("idle");
      await this.refresh();
      wx.showToast({ title: "本单完成", icon: "success" });
    } catch (e) { wx.showModal({ title: "完成失败", content: String((e && (e.errMsg || e.message)) || e).slice(0, 110), showCancel: false }); }
  },
  async setStatus(e) {
    const s = e.currentTarget.dataset.s;
    try { await api.setBarberStatus({ barberId: "b1", status: s }); this.applyStatus(s); }
    catch (err) { wx.showModal({ title: "切不了", content: String((err && (err.errMsg || err.message)) || err).slice(0, 100), showCancel: false }); }
  },
  applyStatus(s) { this.setData({ status: s, tone: TONE[s], statusText: TEXT[s] }); },
  goQueue() { wx.navigateTo({ url: "/pages/barber/queue/index" }); },
  goBoard() { wx.navigateTo({ url: "/pages/barber/board/index" }); },
  goLedger() { wx.navigateTo({ url: "/pages/barber/ledger/index" }); },
  goSettings() { wx.navigateTo({ url: "/pages/barber/settings/index" }); },
});
