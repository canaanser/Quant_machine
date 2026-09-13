// 服务项目管理：新增/修改/上下架（软删：sortOrder = -1 表示下架，不物理删）
exports.main = async (event) => {
  const wxServer = require("wx-server-sdk");
  wxServer.init();
  const db = wxServer.database();
  const p = event || {};
  if (p.action === "save") {
    if (!p.barberId) throw new Error("缺少 barberId");
    const doc = {
      barberId: p.barberId,
      name: String(p.name || "").slice(0, 12),
      defaultDuration: Math.max(1000, Number(p.defaultDuration || 0)),
      price: Math.max(0, Number(p.price || 0)),
      icon: p.icon || "scissors",
      description: String(p.description || "").slice(0, 20),
      sortOrder: Number(p.sortOrder == null ? 99 : p.sortOrder),
    };
    if (!doc.name) throw new Error("项目名不能为空");
    if (p._id) { await db.collection("serviceItems").doc(p._id).update({ data: doc }); return { ok: true, action: "updated", _id: p._id }; }
    const r = await db.collection("serviceItems").add({ data: doc });
    return { ok: true, action: "created", _id: r._id };
  }
  if (p.action === "toggle") {
    if (!p._id) throw new Error("缺少 _id");
    const cur = await db.collection("serviceItems").doc(p._id).get();
    const off = Number((cur.data || {}).sortOrder) < 0;
    await db.collection("serviceItems").doc(p._id).update({ data: { sortOrder: off ? 99 : -1 } });
    return { ok: true, action: off ? "listed" : "unlisted", _id: p._id };
  }
  throw new Error("未知 action：" + p.action);
};
