// 经营者工作台 —— **只放"此刻要干的活"**：当前服务 / 一键状态 / 快捷接单 / 排队（前三位）+ 四个入口。
// 经营与配置类（数据看板 / 流水 / 目标 / 营业时间 / 项目 / 调试）都在各自页面，不再堆这一页。
import { api, priorityLabel } from "../../../utils/cloud.js";

const TONE = { idle: "free", busy: "busy", rest: "rest" };
const TEXT = { idle: "空闲", busy: "服务中", rest: "已打烊" };
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
    relay: { show: false, counting: false, left: 1, pct: 0, dragY: 0, next: { name: "", face: "🧑", serviceName: "", tag: "" } },
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
      this.startRelay();                                  // ★ 完成 → 进入"接力/休息"决策
    } catch (e) { wx.showModal({ title: "完成失败", content: String((e && (e.errMsg || e.message)) || e).slice(0, 110), showCancel: false }); }
  },
  // ★ 接力决策：拖这张卡向上一松手 = 继续接这位；1 秒内不动 = 休息（防误触）
  startRelay() {
    const next = (this.data.queue || []).find((o) => o.status !== "serving");
    if (!next) {
      wx.showToast({ title: "没人排队，先歇会儿", icon: "none" });
      this.setData({ "relay.show": false });
      return;
    }
    this._relayY0 = null; this._relayLeft = 1.0;
    this.setData({
      relay: { show: true, counting: true, left: 1, pct: 0, dragY: 0,
               next: { name: next.name, face: next.face, serviceName: next.serviceName, tag: next.tag } },
    });
    if (this._rt) clearInterval(this._rt);
    this._rt = setInterval(() => {
      this._relayLeft = Math.max(0, this._relayLeft - 0.1);
      this.setData({ "relay.left": Math.ceil(this._relayLeft), "relay.pct": Math.round((1 - this._relayLeft) * 100) });
      if (this._relayLeft <= 0) { clearInterval(this._rt); this._rt = null; this.relayToRest(); }
    }, 100);
  },
  relayStart(e) { this._relayY0 = e.touches[0].clientY; },
  relayMove(e) {
    if (this._relayY0 == null) return;
    const dy = Math.min(0, e.touches[0].clientY - this._relayY0);     // 只允许往上拖
    this.setData({ "relay.dragY": dy });                              // px→rpx 近似即可（视觉反馈）
  },
  async relayEnd(e) {
    const y0 = this._relayY0; this._relayY0 = null;
    const dy = y0 == null ? 0 : (e.changedTouches[0].clientY - y0);
    this.setData({ "relay.dragY": 0 });
    if (dy >= -40) return;                                            // 没往上拖够 → 交给 1 秒计时（进休息）
    // ★ 老板要求：必须**拖到「现在这位」卡片上、且覆盖 ≥50%**才算继续
    const ok = await this.droppedOnNow(e.changedTouches[0].clientY);
    if (!ok) { wx.showToast({ title: "要拖到「现在这位」上松手才算", icon: "none" }); return; }
    {                                                 // 往上一拖并落在目标框上 = 继续
      if (this._rt) { clearInterval(this._rt); this._rt = null; }
      const next = (this.data.queue || []).find((o) => o.status !== "serving");
      if (!next) return this.relayToRest();
      try {
        if (next.status === "reserved") await api.transition({ orderId: next._id, to: "queuing" });
        await api.transition({ orderId: next._id, to: "serving" });
        this.setData({ "relay.show": false });
        this.applyStatus("busy");
        this.refresh();
        wx.showToast({ title: "继续：" + next.name, icon: "success" });
      } catch (err) { wx.showModal({ title: "接不上", content: String((err && (err.errMsg || err.message)) || err).slice(0, 100), showCancel: false }); }
    }
  },
  /** 拖动卡与「现在这位」卡片的重叠比例 ≥ 50% 才算落位 */
  droppedOnNow(clientY) {
    return new Promise((resolve) => {
      wx.createSelectorQuery().in(this).select("#dropNow").boundingClientRect((r) => {
        if (!r) return resolve(false);
        const cardH = 110;                                     // 拖动卡高度（px 近似）
        const top = clientY - cardH / 2, bottom = clientY + cardH / 2;
        const overlap = Math.max(0, Math.min(r.bottom, bottom) - Math.max(r.top, top));
        resolve(overlap / cardH >= 0.5);
      }).exec();
    });
  },
  relayToRest() {
    this.setData({ "relay.counting": false, "relay.pct": 100 });
    this.applyStatus("rest");
    api.setBarberStatus({ barberId: "b1", status: "rest" }).catch(() => {});
  },
  async resumeWork() {
    this.setData({ "relay.show": false });
    try { await api.setBarberStatus({ barberId: "b1", status: "idle" }); this.applyStatus("idle"); } catch (e) {}
    this.refresh();
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
