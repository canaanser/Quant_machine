// 云开发初始化。ENV_ID 留桩：云环境 ID 到手后填这里（或走 DYNAMIC_CURRENT_ENV）。
const ENV_ID = "cloud1-d2g4axdnz488a6d75";   // 云环境 ID（老板 2026-09-14 建）

App({
  // ★ 默认外观 = **极简版 V1**（老板 2026-09-14：先把极简这套摆到手机那条线上，复杂版挪一边当备份）
  globalData: { barberId: "b1", envId: ENV_ID, autoFlow: false, theme: "minimal" },
  onLaunch() {
    // 只有用户**主动切过**才用他的选择；没切过的一律走默认（极简 V1）
    try { const t = wx.getStorageSync("theme"); if (t) this.globalData.theme = t; } catch (e) {}
    if (!wx.cloud) {
      console.error("请使用 2.2.3+ 基础库以使用云能力");
      return;
    }
    wx.cloud.init({
      env: ENV_ID || wx.cloud.DYNAMIC_CURRENT_ENV,   // 没填就跟随当前环境，本地不炸
      traceUser: true,
    });
  },
  // 外观主题：glass（毛玻璃·默认）/ minimal（极简版 V1）。同一份逻辑，只换观感。
  setTheme(t) {
    this.globalData.theme = t === "minimal" ? "minimal" : "glass";
    try { wx.setStorageSync("theme", this.globalData.theme); } catch (e) {}
  },
  themeClass() { return this.globalData.theme === "minimal" ? "theme--minimal" : "theme--glass"; },
  // ★ 调试滚动队列（全局，与页面无关）：每 4 秒自动流转 + 队列少于 4 位自动补客
  setAutoFlow(on) {
    this.globalData.autoFlow = !!on;
    if (this._flow) { clearInterval(this._flow); this._flow = null; }
    if (!on) return;
    const tick = () => {
      wx.cloud.callFunction({ name: "debugTick", data: { barberId: "b1", keepMin: 4 } }).catch(() => {});
    };
    tick();
    this._flow = setInterval(tick, 4000);
  },
});
