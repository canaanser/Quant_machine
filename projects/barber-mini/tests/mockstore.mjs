// 内存版 store：把 shared/orders.js 需要的接口实现出来，测试与本地联调都用它。
export function makeStore(seed = {}) {
  const data = {
    barbers: [...(seed.barbers || [])],
    serviceItems: [...(seed.serviceItems || [])],
    orders: [...(seed.orders || [])],
  };
  return {
    _data: data,
    async getBarber(id) { return data.barbers.find((b) => b._id === id) || null; },
    async getItem(id) { return data.serviceItems.find((s) => s._id === id) || null; },
    async getOrder(id) { return data.orders.find((o) => o._id === id) || null; },
    async listOrders(barberId) { return data.orders.filter((o) => o.barberId === barberId); },
    async insertOrder(o) { data.orders.push({ ...o }); return o; },
    async updateOrder(id, patch, expectUpdatedAt) {
      const i = data.orders.findIndex((o) => o._id === id);
      if (i < 0) throw new Error("订单不存在：" + id);
      if (expectUpdatedAt && Number(data.orders[i].updatedAt) !== Number(expectUpdatedAt)) {
        throw new Error("CAS 失败：订单已被更新");
      }
      data.orders[i] = { ...data.orders[i], ...patch };
      return data.orders[i];
    },
    async updateBarber(id, patch) {
      const i = data.barbers.findIndex((b) => b._id === id);
      if (i < 0) throw new Error("理发师不存在：" + id);
      data.barbers[i] = { ...data.barbers[i], ...patch };
      return data.barbers[i];
    },
  };
}
