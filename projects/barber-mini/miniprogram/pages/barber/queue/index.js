import { api, priorityLabel } from "../../../utils/cloud.js";
Page({
  data: {
    theme: getApp().themeClass(), list: [] },
  onShow() { this.load(); },
  async load() {
    try {
      const r = await api.queue({ barberId: "b1" });
      this.setData({
        serving: (r.serving ? { customerName: r.serving.customerName || "顾客", serviceName: r.serving.serviceName } : null),
        list: (r.list || []).map((o) => ({
          _id: o._id, customerName: o.customerName || "顾客", serviceName: o.serviceName,
          priority: o.priority, status: o.status, tag: priorityLabel(o.priority),
          statusText: ({ reserved: "已预约", queuing: "排队中", serving: "服务中" })[o.status] || o.status,
          tagClass: ({ 0: "pill--gold", 1: "pill--busy", 2: "" })[o.priority] || "",
        })),
      });
    } catch (e) { wx.showToast({ title: "云端未就绪", icon: "none" }); }
  },
});
