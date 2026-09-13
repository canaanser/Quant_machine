// 调试用：让队列自动滚动（完成到点的单 + 自动开始下一位）。上线前停用。
const { debugTick } = require("./orders.js");
const { cloudStore } = require("./cloudstore.js");

exports.main = async (event) => debugTick(cloudStore(), event.barberId, Date.now(), { autoStart: event.autoStart !== false });
