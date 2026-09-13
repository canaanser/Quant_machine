// 云函数薄壳：只做事件解析与云端 store 适配；业务逻辑在 _shared/orders.js（由 npm run sync 生成）。
import { createOrder } from "./_shared/orders.js";
import { cloudStore } from "./cloudstore.js";

export async function main(event) {
  const store = cloudStore(event);
  return createOrder(store, event, () => Date.now());
}
