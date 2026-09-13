// 今日流水：读 orders（客户端只读，写仍然只走云函数）。按完成时间倒序，含单笔详情。
Page({
  data: { today: [], earlier: [], tSum: 0, tCount: 0, tAvg: 0, loading: true },
  onShow() { this.load(); },
  async load() {
    try {
      const db = wx.cloud.database();
      const r = await db.collection("orders")
        .where({ barberId: "b1", status: "completed" })
        .orderBy("actualEndTime", "desc").limit(50).get();
      const startOfDay = new Date(); startOfDay.setHours(0, 0, 0, 0);
      const t0 = startOfDay.getTime();
      const rows = (r.data || []).map((o) => ({
        _id: o._id,
        customerName: o.customerName || "顾客",
        serviceName: o.serviceName || "",
        price: Number(o.price || 0),
        start: o.actualStartTime, end: o.actualEndTime,
        startText: this.hhmm(o.actualStartTime), endText: this.hhmm(o.actualEndTime),
        min: Math.max(1, Math.round((Number(o.actualEndTime || 0) - Number(o.actualStartTime || 0)) / 60000)),
        typeText: ({ woman: "女士", man: "男士", elder: "老人", child: "小孩" })[o.customerType] || "",
      }));
      const today = rows.filter((o) => Number(o.end) >= t0);
      const sum = today.reduce((s, o) => s + o.price, 0);
      this.setData({
        today, earlier: rows.filter((o) => Number(o.end) < t0),
        tSum: sum, tCount: today.length,
        tAvg: today.length ? Math.round(sum / today.length) : 0,
        loading: false,
      });
    } catch (e) { this.setData({ loading: false }); }
  },
  hhmm(ts) { return ts ? new Date(Number(ts)).toTimeString().slice(0, 5) : "--:--"; },
});
