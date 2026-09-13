// 营业设置：今日目标 / 营业状态等（只写这一位理发师的文档）
exports.main = async (event) => {
  const wxServer = require("wx-server-sdk");
  wxServer.init();
  const db = wxServer.database();
  const p = event || {};
  if (!p.barberId) throw new Error("缺少 barberId");
  const patch = {};
  if (p.dailyGoal != null) patch.dailyGoal = Math.max(0, Number(p.dailyGoal));
  if (p.openTime) patch.openTime = String(p.openTime).slice(0, 5);
  if (p.closeTime) patch.closeTime = String(p.closeTime).slice(0, 5);
  if (!Object.keys(patch).length) throw new Error("没有要改的设置");
  await db.collection("barbers").doc(p.barberId).update({ data: patch });
  return { ok: true, patch };
};
