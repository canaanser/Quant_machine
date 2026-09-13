// 排队进度：读云端排队序算"前面几位 + 预计等待"；倒计时用**前端定时器**（契约：不为它加长连接）。
import { api } from "../../../utils/cloud.js";

Page({
  data: { ahead: 0, etaMin: 20, left: 20 * 60 },
  onLoad() {
    this.load();
    this.timer = setInterval(() => {
      const left = Math.max(0, this.data.left - 1);
      this.setData({ left, etaMin: Math.ceil(left / 60) });
    }, 1000);
  },
  async load() {
    try {
      const r = await api.queue({ barberId: "b1" });
      const list = r.list || [];
      const idx = list.findIndex((o) => o.customerOpenid === "me");
      const ahead = idx < 0 ? 0 : idx;
      this.setData({ ahead, etaMin: ahead * 20, left: ahead * 20 * 60 });
    } catch (e) { /* 云端未就绪：保留默认值 */ }
  },
  onUnload() { clearInterval(this.timer); },
});
