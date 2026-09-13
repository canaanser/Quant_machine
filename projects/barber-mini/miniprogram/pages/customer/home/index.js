// 顾客端首页：**三秒看懂忙不忙** —— 顶部实时状态大卡片 + 两个大按钮。
import { watchBarber } from "../../../utils/watch.js";

Page({
  data: { barber: null, waiting: 0, etaMin: 0, unwatch: null },
  onLoad() {
    // 本地先用 mock 渲染（云环境未就绪也不白屏）；连上后 watch 会覆盖它
    this.setData({ barber: { _id: "b1", name: "阿明", status: "busy" }, waiting: 2, etaMin: 20 });
    try {
      const db = wx.cloud.database();
      this.data.unwatch = watchBarber(db, "b1", (b) => { if (b) this.setData({ barber: b }); });
    } catch (e) { /* 云未初始化时静默 */ }
  },
  onUnload() { if (this.data.unwatch) this.data.unwatch(); },
  goBook() { wx.navigateTo({ url: "/pages/customer/book/index" }); },
  joinQueue() { wx.navigateTo({ url: "/pages/customer/progress/index" }); },
});
