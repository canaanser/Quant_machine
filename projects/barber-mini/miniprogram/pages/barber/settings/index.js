// 设置中心：今日目标 / 营业时间 / 服务项目（含预设图标）/ 入口
import { api } from "../../../utils/cloud.js";

const ICONS = [
  { k: "scissors", label: "剪发" }, { k: "perm", label: "烫发" },
  { k: "dye", label: "染发" }, { k: "care", label: "护理" },
];

Page({
  data: {
    theme: getApp().themeClass(),
    icons: ICONS,
    goal: 300, openTime: "09:00", closeTime: "21:00",
    list: [], edit: null, form: { name: "", price: 38, min: 30, icon: "scissors" },
    hideMoney: false, saving: false,
    autoFlow: false,
  },
  onShow() { this.load(); this.setData({ autoFlow: !!getApp().globalData.autoFlow }); },
  toggleFlow(e) {
    const on = e.currentTarget.dataset.v === "on";
    getApp().setAutoFlow(on);
    this.setData({ autoFlow: on });
    wx.showToast({ title: on ? "调试滚动已开" : "已关闭", icon: "none" });
  },
  setThemeTap(e) {
    const t = e.currentTarget.dataset.v;
    getApp().setTheme(t);
    const cls = getApp().themeClass();
    // 让**所有已打开的页面**立刻换装（不然返回上一页还是旧皮）
    try { getCurrentPages().forEach((p) => p.setData && p.setData({ theme: cls })); } catch (err) {}
    this.setData({ theme: cls });
    wx.showToast({ title: t === "minimal" ? "已切到极简 V1" : "已切回毛玻璃", icon: "none" });
  },
  async load() {
    try {
      const db = wx.cloud.database();
      const [b, items] = await Promise.all([
        db.collection("barbers").doc("b1").get(),
        db.collection("serviceItems").where({ barberId: "b1" }).limit(50).get(),
      ]);
      const bar = b.data || {};
      this.setData({
        goal: Number(bar.dailyGoal || 300),
        openTime: bar.openTime || "09:00",
        closeTime: bar.closeTime || "21:00",
        list: (items.data || []).map((x) => ({
          _id: x._id, name: x.name, price: Number(x.price || 0),
          min: Math.max(1, Math.round(Number(x.defaultDuration || 0) / 60000)),
          icon: x.icon || "scissors", on: Number(x.sortOrder) >= 0,
        })),
      });
    } catch (e) { /* 云端未就绪 */ }
  },
  // 目标：弹输入框（银行 App 那种设置方式）
  setGoal() {
    wx.showModal({ title: "今日目标（元）", editable: true, placeholderText: String(this.data.goal),
      success: async (r) => {
        if (!r.confirm || !r.content) return;
        const g = Math.max(0, Number(r.content) || 0);
        try { await api.saveSettings({ barberId: "b1", dailyGoal: g }); this.setData({ goal: g }); wx.showToast({ title: "已保存", icon: "success" }); }
        catch (e) { wx.showToast({ title: "保存失败", icon: "none" }); }
      } });
  },
  onTime(e) {
    const k = e.currentTarget.dataset.k;
    this.setData({ [k]: e.detail.value });
  },
  async saveHours() {
    try {
      await api.saveSettings({ barberId: "b1", openTime: this.data.openTime, closeTime: this.data.closeTime });
      wx.showToast({ title: "营业时间已保存", icon: "success" });
    } catch (e) { wx.showToast({ title: "保存失败", icon: "none" }); }
  },
  toggleEye() { this.setData({ hideMoney: !this.data.hideMoney }); },
  // 项目管理（预设图标可选）
  openNew() { this.setData({ edit: "new", form: { name: "", price: 38, min: 30, icon: "scissors" } }); },
  openEdit(e) {
    const it = this.data.list.find((x) => x._id === e.currentTarget.dataset.id);
    this.setData({ edit: it._id, form: { name: it.name, price: it.price, min: it.min, icon: it.icon } });
  },
  close() { this.setData({ edit: null }); },
  onInput(e) { this.setData({ ["form." + e.currentTarget.dataset.k]: e.detail.value }); },
  pickIcon(e) { this.setData({ "form.icon": e.currentTarget.dataset.k }); },
  async save() {
    const { edit, form } = this.data;
    if (!form.name) return wx.showToast({ title: "填个名字", icon: "none" });
    this.setData({ saving: true });
    try {
      await api.saveItem({ action: "save", _id: edit === "new" ? undefined : edit, barberId: "b1",
        name: form.name, price: Number(form.price), defaultDuration: Number(form.min) * 60000, icon: form.icon });
      this.setData({ edit: null });
      wx.showToast({ title: "已保存", icon: "success" });
      await this.load();
    } catch (e) {
      wx.showModal({ title: "保存失败", content: String((e && (e.errMsg || e.message)) || e).slice(0, 110), showCancel: false });
    } finally { this.setData({ saving: false }); }
  },
  async toggle(e) {
    try { await api.saveItem({ action: "toggle", _id: e.currentTarget.dataset.id }); await this.load(); }
    catch (err) { wx.showToast({ title: "操作失败", icon: "none" }); }
  },
  goLedger() { wx.navigateTo({ url: "/pages/barber/ledger/index" }); },
});
