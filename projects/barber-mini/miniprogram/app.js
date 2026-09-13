// 云开发初始化。ENV_ID 留桩：云环境 ID 到手后填这里（或走 DYNAMIC_CURRENT_ENV）。
const ENV_ID = "cloud1-d2g4axdnz488a6d75";   // 云环境 ID（老板 2026-09-14 建）

App({
  globalData: { barberId: "b1", envId: ENV_ID },
  onLaunch() {
    if (!wx.cloud) {
      console.error("请使用 2.2.3+ 基础库以使用云能力");
      return;
    }
    wx.cloud.init({
      env: ENV_ID || wx.cloud.DYNAMIC_CURRENT_ENV,   // 没填就跟随当前环境，本地不炸
      traceUser: true,
    });
  },
});
