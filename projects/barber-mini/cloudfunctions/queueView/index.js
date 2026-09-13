// 云函数：返回**已排好序**的在队订单（排序/优先级逻辑在 orders.js，客户端不重写）。
const { queueView } = require("./orders.js");
const { cloudStore } = require("./cloudstore.js");

exports.main = async (event) => {
  const list = await queueView(cloudStore(), event.barberId, Date.now());
  return { list, count: list.length, serving: list.find((o) => o.status === "serving") || null };
};

