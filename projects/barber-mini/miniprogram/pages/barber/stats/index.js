import { api } from "../../../utils/cloud.js";
Page({
  data: { s: null },
  async onLoad() {
    try { this.setData({ s: await api.stats({ barberId: "b1", fromTs: 0, toTs: 0 }) }); }
    catch (e) { this.setData({ s: null }); }
  },
});
