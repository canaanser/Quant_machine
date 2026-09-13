// 预约三步（不跳新页）：选时间 → 选项目 → 选客人属性 → 确认。时间轴三色：可约/已约/不可约。
import { api } from "../../../utils/cloud.js";

const HOUR = 3600 * 1000;
export function buildSlots(dayStart, orders, stepMin = 40, count = 8) {
  const step = stepMin * 60 * 1000;
  const busy = (t) => (orders || []).some((o) =>
    ["reserved", "queuing", "serving"].includes(o.status) &&
    t < Number(o.appointmentTime || 0) + Number(o.duration || 0) &&
    Number(o.appointmentTime || 0) < t + step);
  const out = [];
  for (let i = 0; i < count; i++) {
    const t = dayStart + i * step;
    out.push({ t, label: new Date(t + 8 * HOUR).toISOString().slice(11, 16), state: busy(t) ? "busy" : "free" });
  }
  return out;
}

Page({
  data: { step: 1, slots: [], pickedSlot: null, items: [], pickedItem: null, types: [], pickedType: null },
  onLoad() {
    const dayStart = new Date(new Date().toDateString()).getTime() + 9 * HOUR;   // 今天 09:00 起
    this.setData({
      slots: buildSlots(dayStart, []),
      items: [
        { _id: "s1", name: "剪发", price: 38, defaultDuration: 40 },
        { _id: "s2", name: "烫发", price: 288, defaultDuration: 150 },
      ],
      types: [{ key: "woman", label: "女士" }, { key: "man", label: "男士" }, { key: "elder", label: "老人" }, { key: "child", label: "小孩" }],
    });
  },
  pickSlot(e) { this.setData({ pickedSlot: e.currentTarget.dataset.t, step: 2 }); },
  pickItem(e) { this.setData({ pickedItem: e.currentTarget.dataset.id, step: 3 }); },
  pickType(e) { this.setData({ pickedType: e.currentTarget.dataset.key }); },
  async submit() {
    const { pickedSlot, pickedItem, pickedType } = this.data;
    if (!pickedSlot || !pickedItem || !pickedType) return wx.showToast({ title: "还差一步", icon: "none" });
    try {
      await api.createOrder({
        barberId: "b1", serviceItemId: pickedItem, customerType: pickedType,
        customerOpenid: "me", appointmentTime: Number(pickedSlot),
      });
      wx.showToast({ title: "预约成功", icon: "success" });
      setTimeout(() => wx.switchTab({ url: "/pages/customer/home/index" }), 800);
    } catch (e) { wx.showToast({ title: String(e.errMsg || e).slice(0, 20), icon: "none" }); }
  },
});
