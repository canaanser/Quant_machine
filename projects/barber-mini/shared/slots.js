// 时间槽与时长计算 —— **唯一真源**（云函数做冲突检测时用它，前端预览也用它）。
export const STEP_MS = 10 * 60 * 1000;   // 10 分钟步进

export function overlaps(aStart, aDur, bStart, bDur) {
  const as = Number(aStart || 0), ad = Number(aDur || 0);
  const bs = Number(bStart || 0), bd = Number(bDur || 0);
  if (!ad || !bd) return false;
  return as < bs + bd && bs < as + ad;
}

/** 该时段是否与"占用中的单"冲突（completed/cancelled 不占）。 */
export function hasConflict(start, duration, orders) {
  const busy = ["reserved", "queuing", "serving"];
  return (orders || []).some((o) => busy.includes(o.status) &&
    overlaps(start, duration, Number(o.appointmentTime || o.actualStartTime || 0), o.duration));
}

/** 从 fromTs 起找第一个不冲突的时长槽（步进 STEP_MS，最多找 maxSteps 步）。 */
export function findFreeSlot(fromTs, duration, orders, opts = {}) {
  const step = Number(opts.step || STEP_MS);
  const maxSteps = Number(opts.maxSteps || 36);         // 默认最多往后找 6 小时
  let t = Number(fromTs || 0);
  for (let i = 0; i < maxSteps; i++) {
    if (!hasConflict(t, duration, orders)) return t;
    t += step;
  }
  return null;
}

export function endOf(start, duration) {
  return Number(start || 0) + Number(duration || 0);
}
