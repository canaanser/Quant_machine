// 排队进度：读云端排队序算"我的位置 + 前面的人 + 预计等待"；倒计时用前端定时器（契约：不为它加长连接）。
import { api, priorityLabel } from "../../../utils/cloud.js";

const MIN = 60 * 1000;
const TAG_CLASS = { 0: "pill--gold", 1: "pill--busy", 2: "" };
const STATUS_TEXT = { reserved: "已预约", queuing: "排队中", serving: "服务中" };

Page({
  data: {
    list: [], front: [], ahead: 0, etaMin: 0, leftMin: 0, progressPct: 8,
    countdown: "--:--", updated: "--:--",
    loading: true,
    me: { initial: "我", serviceName: "", statusText: "排队中", tag: "现场", tagClass: "" },
  },
  onLoad() {
    // ★ 秒开：先用上一页带过来的单把界面填上（不空白），再拉云端队伍校正
    const passed = (getApp().globalData || {}).lastOrder;
    if (passed) {
      this.setData({
        me: { initial: "我", serviceName: passed.serviceName || "", statusText: "排队中",
              tag: priorityLabel(passed.priority), tagClass: TAG_CLASS[passed.priority] || "" },
      });
    }
    this.load();
    this.timer = setInterval(() => this.tick(), 1000);
  },
  onShow() { this.load(); },
  onUnload() { clearInterval(this.timer); },
  async load() {
    let list = [];
    try {
      const r = await api.queue({ barberId: "b1" });
      list = r.list || [];
    } catch (e) { /* 云端未就绪：留空态 */ }

    const idx = list.findIndex((o) => o.customerOpenid === "me");
    const mine = idx >= 0 ? list[idx] : null;
    const ahead = idx < 0 ? 0 : idx;
    const etaMin = ahead * 20;
    this.setData({
      list,
      front: list.slice(0, Math.max(0, idx)).map((o) => ({
        _id: o._id, customerName: o.customerName || "顾客", serviceName: o.serviceName,
        statusText: STATUS_TEXT[o.status] || o.status,
        tag: priorityLabel(o.priority), tagClass: TAG_CLASS[o.priority] || "",
      })),
      ahead, etaMin, leftMin: etaMin,
      progressPct: list.length ? Math.round(((idx + 1) / list.length) * 100) : 8,
      updated: new Date().toTimeString().slice(0, 5),
      loading: false,
      me: {
        initial: (mine && mine.customerName ? mine.customerName.slice(0, 1) : "我"),
        serviceName: mine ? mine.serviceName : "",
        statusText: mine ? (STATUS_TEXT[mine.status] || mine.status) : "排队中",
        tag: mine ? priorityLabel(mine.priority) : "现场",
        tagClass: mine ? (TAG_CLASS[mine.priority] || "") : "",
      },
    });
  },
  tick() {
    const total = Math.max(0, this.data.etaMin * 60);
    const next = Math.max(0, (this._left == null ? total : this._left) - 1);
    this._left = next;
    const m = Math.floor(next / 60), s = next % 60;
    this.setData({ countdown: (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s, leftMin: Math.ceil(next / 60) });
  },
  back() { wx.switchTab({ url: "/pages/customer/home/index" }); },
  async cancel() {
    const mine = this.data.list.find((o) => o.customerOpenid === "me");
    if (!mine) return wx.switchTab({ url: "/pages/customer/home/index" });
    const res = await new Promise((resolve) => wx.showModal({
      title: "取消排队", content: "确定不排了吗？", success: (r) => resolve(r.confirm), fail: () => resolve(false),
    }));
    if (!res) return;
    try {
      await api.transition({ orderId: mine._id, to: "cancelled" });
      wx.showToast({ title: "已取消", icon: "success" });
      setTimeout(() => wx.switchTab({ url: "/pages/customer/home/index" }), 900);
    } catch (e) {
      wx.showModal({ title: "取消失败", content: String((e && (e.errMsg || e.message)) || e).slice(0, 100), showCancel: false });
    }
  },
});
