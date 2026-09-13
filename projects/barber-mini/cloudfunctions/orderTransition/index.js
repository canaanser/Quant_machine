const { transitionOrder } = require("./orders.js");
const { cloudStore } = require("./cloudstore.js");
exports.main = async (event) => transitionOrder(cloudStore(), event, () => Date.now());


