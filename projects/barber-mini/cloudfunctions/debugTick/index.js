// 调试用：让队列自动滚动（完成到点的单 + 自动开始下一位）。上线前停用。
const { debugTick } = require("./orders.js");
const { cloudStore } = require("./cloudstore.js");

// 调试用：自动流转 + **自动补客**（队列少于 keepMin 时造一个现场客，避免"空单/队列空转"）
const { createOrder } = require("./orders.js");
const { cloudStore } = require("./cloudstore.js");

const NAMES = ["小王", "李姐", "张叔", "陈阿姨", "小林", "阿强", "周哥", "小美"];
const TYPES = ["woman", "man", "elder", "child"];

exports.main = async (event) => {
  const store = cloudStore();
  const barberId = event.barberId || "b1";
  const out = await debugTick(store, barberId, Date.now(), { autoStart: event.autoStart !== false });

  if (event.keepMin) {
    const { queueView } = require("./orders.js");
    const q = await queueView(store, barberId, Date.now());
    const need = Math.max(0, Number(event.keepMin) - q.length);
    out.filled = [];
    for (let i = 0; i < need; i++) {
      const n = NAMES[Math.floor(Math.random() * NAMES.length)];
      const t = TYPES[Math.floor(Math.random() * TYPES.length)];
      const r = await createOrder(store, { barberId, serviceItemId: event.serviceItemId || "s1",
        customerOpenid: "auto_" + Date.now() + "_" + i, customerName: n, customerType: t }, () => Date.now());
      out.filled.push(r.order._id);
    }
  }
  return out;
};
