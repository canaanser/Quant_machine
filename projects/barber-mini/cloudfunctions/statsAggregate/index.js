const { aggregateStats } = require("./orders.js");
const { cloudStore } = require("./cloudstore.js");
exports.main = async (event) => aggregateStats(cloudStore(), event);


