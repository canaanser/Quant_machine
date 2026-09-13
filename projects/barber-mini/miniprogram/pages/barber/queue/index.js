import { api, priorityLabel } from "../../../utils/cloud.js";
Page({
  data: { list: [] },
  onShow() { this.load(); },
  async load() {
    try {
      const r = await api.queue({ barberId: "b1" });
      this.setData({
        list: (r.list || []).map((o) => ({
          _id: o._id, customerName: o.customerName || "顾客", serviceName: o.serviceName,
          priority: o.priority, status: o.status, tag: priorityLabel(o.priority),
        })),
      });
    } catch (e) { wx.showToast({ title: "云端未就绪", icon: "none" }); }
  },
});
