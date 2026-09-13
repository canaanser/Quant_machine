// 理发师工作台：当前服务卡 + 一键状态 + 快捷接单（**接单 ≤3 击：选客人类型 → 选项目 → 确认**）
import { api } from "../../../utils/cloud.js";

const TYPES = [
  { key: "woman", label: "女士", icon: "👩" },
  { key: "man", label: "男士", icon: "👨" },
  { key: "elder", label: "老人", icon: "🧓" },
  { key: "child", label: "小孩", icon: "🧒" },
];

Page({
  data: {
    barber: { _id: "b1", name: "阿明", status: "idle", currentOrderId: null },
    items: [
      { _id: "s1", name: "剪发", defaultDuration: 40, price: 38 },
      { _id: "s2", name: "烫发", defaultDuration: 150, price: 288 },
      { _id: "s3", name: "染发", defaultDuration: 120, price: 258 },
      { _id: "s4", name: "护理", defaultDuration: 60, price: 128 },
    ],
    queue: [], types: TYPES, picked: null, itemPicked: null, elapsedMin: 0,
  },
  onLoad() { this.refresh(); },
  onShow() { this.refresh(); },
  async refresh() {
    try {
      const r = await api.stats({ barberId: this.data.barber._id, fromTs: 0, toTs: 0 });
      this.setData({ stats: r });
    } catch (e) { /* 云环境未就绪时静默，界面用本地态 */ }
  },
  pickType(e) { this.setData({ picked: e.currentTarget.dataset.key }); },          // 第 1 击
  pickItem(e) { this.setData({ itemPicked: e.currentTarget.dataset.id }); },       // 第 2 击
  async confirmStart() {                                                          // 第 3 击
    const { picked, itemPicked, barber } = this.data;
    if (!picked || !itemPicked) return wx.showToast({ title: "先选客人类型和项目", icon: "none" });
    try {
      const r = await api.createOrder({ barberId: barber._id, serviceItemId: itemPicked, customerType: picked, customerOpenid: "walkin_" + Date.now() });
      await api.transition({ orderId: r.order._id, to: "serving" });
      wx.showToast({ title: "已开始服务", icon: "success" });
      this.setData({ picked: null, itemPicked: null });
    } catch (e) { wx.showToast({ title: String(e.errMsg || e).slice(0, 20), icon: "none" }); }
  },
  async finish() {
    const id = this.data.barber.currentOrderId;
    if (!id) return;
    await api.transition({ orderId: id, to: "completed" });
    wx.showToast({ title: "本单完成", icon: "success" });
  },
  async setStatus(e) { await api.setBarberStatus({ barberId: this.data.barber._id, status: e.currentTarget.dataset.s }); },
});
