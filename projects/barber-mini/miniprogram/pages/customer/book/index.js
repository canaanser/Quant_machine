// 预约三步：选时间 → 选项目 → 选客人属性 → 确认。写操作只走云函数。
import { api } from "../../../utils/cloud.js";

const MIN = 60 * 1000;
const TYPES = [
  { k: "woman", label: "女士", ico: "👩" },
  { k: "man", label: "男士", ico: "👨" },
  { k: "elder", label: "老人", ico: "🧓" },
  { k: "child", label: "小孩", ico: "🧒" },
];

Page({
  data: {
    step: 1, slots: [], items: [], types: TYPES,
    pickedSlot: null, pickedItem: null, pickedType: null,
    summary: { time: "未选", item: "未选", type: "未选", price: 0 },
    canSubmit: false,
  },
  onLoad() { this.buildSlots(); },
  buildSlots() {
    const base = new Date(); base.setMinutes(0, 0, 0);
    const slots = [];
    for (let i = 1; i <= 8; i++) {
      const ts = base.getTime() + i * 40 * MIN;
      slots.push({ ts, label: new Date(ts).toTimeString().slice(0, 5), busy: false });
    }
    this.setData({
      slots,
      items: [
        { _id: "s1", name: "剪发", price: 38, duration: 40, icon: "✂️" },
        { _id: "s2", name: "烫发", price: 288, duration: 150, icon: "🌀" },
        { _id: "s3", name: "染发", price: 258, duration: 120, icon: "🎨" },
      ],
    });
  },
  pickSlot(e) { this.setData({ pickedSlot: Number(e.currentTarget.dataset.ts), step: 2 }); this.syncSummary(); },
  pickItem(e) { this.setData({ pickedItem: e.currentTarget.dataset.id, step: 3 }); this.syncSummary(); },
  pickType(e) { this.setData({ pickedType: e.currentTarget.dataset.k }); this.syncSummary(); },
  syncSummary() {
    const { slots, items, types, pickedSlot, pickedItem, pickedType } = this.data;
    const slot = slots.find((s) => s.ts === pickedSlot);
    const item = items.find((i) => i._id === pickedItem);
    const type = types.find((t) => t.k === pickedType);
    this.setData({
      summary: {
        time: slot ? slot.label : "未选",
        item: item ? item.name + "（" + item.duration + " 分钟）" : "未选",
        type: type ? type.label : "未选",
        price: item ? item.price : 0,
      },
      canSubmit: !!(pickedSlot && pickedItem && pickedType),
    });
  },
  async submit() {
    const { pickedSlot, pickedItem, pickedType, canSubmit } = this.data;
    if (!canSubmit) return wx.showToast({ title: "还有没选的", icon: "none" });
    try {
      await api.createOrder({ barberId: "b1", serviceItemId: pickedItem, customerType: pickedType,
        customerOpenid: "me", customerName: "我", appointmentTime: pickedSlot });
      wx.showToast({ title: "预约成功", icon: "success" });
      setTimeout(() => wx.switchTab({ url: "/pages/customer/home/index" }), 900);
    } catch (e) {
      wx.showToast({ title: "云端未就绪或时段被占", icon: "none" });
    }
  },
});
