// 时间统一：**24 小时制**（老板 2026-09-14 明确：不要 12 小时制）
export function hhmm(ts) {
  if (!ts) return "--:--";
  const d = new Date(Number(ts));
  const h = d.getHours(), m = d.getMinutes();
  return (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m;
}
export const SLOT_MIN = 30;          // 可约时段：**半小时一格**
export const SLOT_MS = SLOT_MIN * 60 * 1000;
