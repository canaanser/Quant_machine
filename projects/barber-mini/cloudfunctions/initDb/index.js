// 一次性初始化：建三个集合 + 灌最小种子数据（幂等，可重复跑）。
// 只在 confirm === "yes" 时动手 —— 防止误触把线上库当测试库。
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);

const COLLECTIONS = ["barbers", "serviceItems", "orders"];

const SEED_BARBER = { _id: "b1", openid: "owner_b1", name: "阿明", avatar: "", status: "idle",
  currentOrderId: null, autoAccept: false, serviceItems: [], createdAt: 0 };

const SEED_ITEMS = [
  { _id: "s1", barberId: "b1", name: "剪发", defaultDuration: 40 * 60 * 1000, price: 38, icon: "scissors", description: "洗剪吹", sortOrder: 1 },
  { _id: "s2", barberId: "b1", name: "烫发", defaultDuration: 150 * 60 * 1000, price: 288, icon: "perm", description: "含造型", sortOrder: 2 },
  { _id: "s3", barberId: "b1", name: "染发", defaultDuration: 120 * 60 * 1000, price: 258, icon: "dye", description: "纯色", sortOrder: 3 },
  { _id: "s4", barberId: "b1", name: "护理", defaultDuration: 60 * 60 * 1000, price: 128, icon: "care", description: "头皮护理", sortOrder: 4 },
];

export async function main(event) {
  if (!event || event.confirm !== "yes") {
    return { ok: false, hint: '这是初始化函数；确认要建库就传 {"confirm":"yes"} 再跑一次。' };
  }
  const wxServer = require("wx-server-sdk");
  wxServer.init();
  const db = wxServer.database();
  const done = [], skipped = [];

  for (const name of COLLECTIONS) {
    try { await db.createCollection(name); done.push("created:" + name); }
    catch (e) { skipped.push("exists:" + name); }   // 已存在会报错，属正常
  }

  // 种子：只在空集合里插，避免覆盖你已有的数据
  const barbers = await db.collection("barbers").count();
  if (barbers.total === 0) { await db.collection("barbers").add({ data: SEED_BARBER }); done.push("seeded:barber b1"); }
  else skipped.push("barbers 已有 " + barbers.total + " 条，不动");

  const items = await db.collection("serviceItems").count();
  if (items.total === 0) {
    for (const it of SEED_ITEMS) await db.collection("serviceItems").add({ data: it });
    done.push("seeded:serviceItems x" + SEED_ITEMS.length);
  } else skipped.push("serviceItems 已有 " + items.total + " 条，不动");

  return { ok: true, done, skipped };
}
