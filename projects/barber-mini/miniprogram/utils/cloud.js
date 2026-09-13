// 云函数调用封装：**客户端唯一写入口**（契约：不直写 orders/barbers）。
//
// ⚠️ 2026-09-14 踩坑：这里原来 import 了 `../../shared/priority.js` ——
//   那个文件在 `miniprogramRoot`（miniprogram/）**之外**，小程序打包不允许，运行时报
//   `can not find module : require args is ../../shared/priority.js` → **整页白屏**。
//   修法：客户端**不引外部逻辑**（真正的计算都在云端 `shared/` 一份），这里只留**展示用常量**。
const PRIORITY = { PREPAID: 0, RESERVED: 1, WALKIN: 2 };

export function call(name, data) {
  return new Promise((resolve, reject) => {
    wx.cloud.callFunction({ name, data, success: (r) => resolve(r.result), fail: reject });
  });
}

export const api = {
  createOrder: (d) => call("orderCreate", d),
  transition: (d) => call("orderTransition", d),
  setBarberStatus: (d) => call("barberStatusSet", d),
  stats: (d) => call("statsAggregate", d),
  queue: (d) => call("queueView", d),
  debugTick: (d) => call("debugTick", d),   // 调试专用：自动流转（生产环境不部署这个云函数）
  saveItem: (d) => call("serviceItemUpsert", d),
  saveSettings: (d) => call("barberSettings", d),
};

export { PRIORITY };
export const priorityLabel = (p) => (Number(p) === 0 ? "预付款优先" : Number(p) === 1 ? "已预约" : "现场排队");
