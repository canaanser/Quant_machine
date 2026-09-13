// 预约三步：选时间 → 选项目 → 选客人属性 → 确认。写操作只走云函数。
import { api } from "../../../utils/cloud.js";
import { hhmm, SLOT_MS } from "../../../utils/time.js";

const MIN = 60 * 1000;
const TYPES = [
  { k: "woman", label: "女士", ico: "👩" },
  { k: "man", label: "男士", ico: "👨" },
  { k: "elder", label: "老人", ico: "🧓" },
  { k: "child", label: "小孩", ico: "🧒" },
];

Page({
  data: {
    theme: getApp().themeClass(),
    step: 1, slots: [], items: [], types: TYPES,
    pickedSlot: null, pickedItem: null, pickedType: null,
    summary: { time: "未选", item: "未选", type: "未选", price: 0 },
    canSubmit: false,
  },
  onLoad(options) {
    // ★ 接住首页选好的「我是谁 / 做什么」——不用让顾客再选一遍
    const patch = {};
    if (options && options.item) patch.pickedItem = options.item;
    if (options && options.type) patch.pickedType = options.type;
    if (Object.keys(patch).length) this.setData(patch);
    this.buildSlots();
    this.syncSummary();
  },
  buildSlots() {
    const base = new Date(); base.setMinutes(0, 0, 0);
    const slots = [];
    for (let i = 1; i <= 8; i++) {
      const ts = base.getTime() + i * SLOT_MS;      // ★ 半小时一格（原来 40 分钟，太怪）
      slots.push({ ts, label: hhmm(ts), busy: false });
    }
    this.setData({
      slots,
      items: [
        { _id: "s1", name: "剪发", price: 38, duration: 40, icon: "scissors" },
        { _id: "s2", name: "烫发", price: 288, duration: 150, icon: "perm" },
        { _id: "s3", name: "染发", price: 258, duration: 120, icon: "dye" },
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
    const { pickedSlot, pickedItem, pickedType } = this.data;
    // 不依赖派生标志（canSubmit 可能因为渲染时序没同步），直接判三要素
    if (pickedSlot == null || !pickedItem || !pickedType) {
      return wx.showToast({ title: "还有没选的", icon: "none" });
    }
    try {
      wx.showLoading({ title: "提交中…", mask: true });
      const r = await api.createOrder({ barberId: "b1", serviceItemId: pickedItem, customerType: pickedType,
        customerOpenid: "me", customerName: "我", appointmentTime: pickedSlot });
      getApp().globalData.lastOrder = r && r.order;
      wx.showToast({ title: "预约成功", icon: "success" });
      setTimeout(() => wx.switchTab({ url: "/pages/customer/home/index" }), 1200);
    } catch (e) {
      const msg = String((e && (e.errMsg || e.message)) || e);
      wx.showModal({ title: "预约失败", content: msg.slice(0, 120), showCancel: false });
    } finally { wx.hideLoading(); }
  },
});
