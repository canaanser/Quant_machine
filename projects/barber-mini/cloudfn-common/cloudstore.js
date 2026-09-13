// 云端 store 适配（**真源**；由 npm run sync 复制进每个云函数目录）。
// 把 shared/orders.js 需要的接口映射到 wx-server-sdk；环境 ID 不硬编（走 DYNAMIC_CURRENT_ENV）。
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);

let cloud = null;
function init() {
  if (cloud) return cloud;
  const wxServer = require("wx-server-sdk");   // 云端才有；本地/测试不碰它
  wxServer.init();
  cloud = wxServer;
  return cloud;
}

export function cloudStore() {
  const c = init();
  const db = c.database();
  return {
    async getBarber(id) { const r = await db.collection("barbers").doc(id).get().catch(() => null); return r && r.data; },
    async getItem(id) { const r = await db.collection("serviceItems").doc(id).get().catch(() => null); return r && r.data; },
    async getOrder(id) { const r = await db.collection("orders").doc(id).get().catch(() => null); return r && r.data; },
    async listOrders(barberId) { const r = await db.collection("orders").where({ barberId }).get(); return r.data || []; },
    async insertOrder(o) { await db.collection("orders").add({ data: o }); return o; },
    async updateOrder(id, patch, expectUpdatedAt) {
      const cur = await this.getOrder(id);
      if (expectUpdatedAt && Number(cur.updatedAt) !== Number(expectUpdatedAt)) throw new Error("CAS 失败：订单已被更新");
      await db.collection("orders").doc(id).update({ data: patch });
      return { ...cur, ...patch };
    },
    async updateBarber(id, patch) { await db.collection("barbers").doc(id).update({ data: patch }); return patch; },
  };
}
