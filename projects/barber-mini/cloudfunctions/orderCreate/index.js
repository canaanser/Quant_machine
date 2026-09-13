const { createOrder } = require("./orders.js");
const { cloudStore } = require("./cloudstore.js");
exports.main = async (event) => createOrder(cloudStore(), event, () => Date.now());


