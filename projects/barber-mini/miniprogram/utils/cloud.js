// 云函数调用封装：**客户端唯一写入口**（契约：不直写 orders/barbers）。
import { PRIORITY } from "../../shared/priority.js";

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
};

export { PRIORITY };
export const priorityLabel = (p) => (Number(p) === 0 ? "预付款优先" : Number(p) === 1 ? "已预约" : "现场排队");
