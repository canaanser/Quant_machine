// 排队进度：前面几人 + 预计等待；倒计时用**前端定时器**（契约：不为它加长连接）。
Page({
  data: { ahead: 2, etaMin: 35, left: 35 * 60 },
  onLoad() {
    this.timer = setInterval(() => {
      const left = Math.max(0, this.data.left - 1);
      this.setData({ left, etaMin: Math.ceil(left / 60) });
    }, 1000);
  },
  onUnload() { clearInterval(this.timer); },
  fmt() { const m = Math.floor(this.data.left / 60), s = this.data.left % 60; return m + " 分 " + s + " 秒"; },
});
