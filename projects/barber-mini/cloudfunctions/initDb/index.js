// 一次性初始化（需传 {"confirm":"yes"}）：建集合 + 灌最小种子。幂等。
const COLLECTIONS = ["barbers", "serviceItems", "orders"];
const SEED_BARBER = { _id: "b1", openid: "owner_b1", name: "阿明", avatar: "", status: "idle",
  currentOrderId: null, autoAccept: false, serviceItems: [], createdAt: 0 };
const SEED_ITEMS = [
  { _id: "s1", barberId: "b1", name: "剪发", defaultDuration: 2400000, price: 38, icon: "scissors", description: "洗剪吹", sortOrder: 1 },
  { _id: "s2", barberId: "b1", name: "烫发", defaultDuration: 9000000, price: 288, icon: "perm", description: "含造型", sortOrder: 2 },
  { _id: "s3", barberId: "b1", name: "染发", defaultDuration: 7200000, price: 258, icon: "dye", description: "纯色", sortOrder: 3 },
  { _id: "s4", barberId: "b1", name: "护理", defaultDuration: 3600000, price: 128, icon: "care", description: "头皮护理", sortOrder: 4 },
];

exports.main = async (event) => {
  if (!event || event.confirm !== "yes") {
    return { ok: false, hint: '确认要建库就传 {"confirm":"yes"} 再跑一次。' };
  }
  const wxServer = require("wx-server-sdk");
  wxServer.init();
  const db = wxServer.database();
  const done = [], skipped = [];
  for (const name of COLLECTIONS) {
    try { await db.createCollection(name); done.push("created:" + name); }
    catch (e) { skipped.push("exists:" + name); }
  }
  const b = await db.collection("barbers").count();
  if (b.total === 0) { await db.collection("barbers").add({ data: SEED_BARBER }); done.push("seeded:barber"); }
  else skipped.push("barbers 已有 " + b.total + " 条");
  const it = await db.collection("serviceItems").count();
  if (it.total === 0) { for (const x of SEED_ITEMS) await db.collection("serviceItems").add({ data: x }); done.push("seeded:items"); }
  else skipped.push("serviceItems 已有 " + it.total + " 条");
  return { ok: true, done, skipped };
};


