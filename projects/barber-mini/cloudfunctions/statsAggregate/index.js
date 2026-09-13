import { aggregateStats } from "./_shared/orders.js";
import { cloudStore } from "./cloudstore.js";

export async function main(event) {
  const store = cloudStore(event);
  return aggregateStats(store, event);
}
