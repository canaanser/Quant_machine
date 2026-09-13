// 服务项目管理：改价/改时长/上下架/新增。写操作走云函数 serviceItemUpsert。
import { api } from "../../../utils/cloud.js";

Page({
  data: { list: [], edit: null, form: { name: "", price: 0, min: 10, icon: "scissors" }, saving: false },
  onShow() { this.load(); },
  async load() {
    try {
      const db = wx.cloud.database();
      const r = await db.collection("serviceItems").where({ barberId: "b1" }).limit(50).get();
      this.setData({ list: (r.data || []).map((x) => ({
        _id: x._id, name: x.name, price: Number(x.price || 0),
        min: Math.max(1, Math.round(Number(x.defaultDuration || 0) / 60000)),
        icon: x.icon || "scissors", on: Number(x.sortOrder) >= 0,
      })) });
    } catch (e) { /* 云端未就绪 */ }
  },
  openNew() { this.setData({ edit: "new", form: { name: "", price: 38, min: 10, icon: "scissors" } }); },
  openEdit(e) {
    const it = this.data.list.find((x) => x._id === e.currentTarget.dataset.id);
    this.setData({ edit: it._id, form: { name: it.name, price: it.price, min: it.min, icon: it.icon } });
  },
  close() { this.setData({ edit: null }); },
  onInput(e) { this.setData({ ["form." + e.currentTarget.dataset.k]: e.detail.value }); },
  async save() {
    const { edit, form } = this.data;
    if (!form.name) return wx.showToast({ title: "填个名字", icon: "none" });
    this.setData({ saving: true });
    try {
      await api.saveItem({ action: "save", _id: edit === "new" ? undefined : edit, barberId: "b1",
        name: form.name, price: Number(form.price), defaultDuration: Number(form.min) * 60000, icon: form.icon });
      wx.showToast({ title: "已保存", icon: "success" });
      this.setData({ edit: null });
      await this.load();
    } catch (e) {
      wx.showModal({ title: "保存失败", content: String((e && (e.errMsg || e.message)) || e).slice(0, 110), showCancel: false });
    } finally { this.setData({ saving: false }); }
  },
  async toggle(e) {
    const id = e.currentTarget.dataset.id;
    try { await api.saveItem({ action: "toggle", _id: id }); await this.load(); }
    catch (err) { wx.showToast({ title: "操作失败", icon: "none" }); }
  },
});
