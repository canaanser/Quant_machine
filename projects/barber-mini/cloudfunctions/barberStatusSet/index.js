const { setBarberStatus } = require("./orders.js");
const { cloudStore } = require("./cloudstore.js");
exports.main = async (event) => setBarberStatus(cloudStore(), event);


