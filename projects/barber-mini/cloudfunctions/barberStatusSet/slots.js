// 时间槽与时长计算 —— **唯一真源**（CommonJS）
const STEP_MS = 10 * 60 * 1000;
const BUSY = ["reserved", "queuing", "serving"];

function overlaps(aStart, aDur, bStart, bDur) {
  const as = Number(aStart || 0), ad = Number(aDur || 0);
  const bs = Number(bStart || 0), bd = Number(bDur || 0);
  if (!ad || !bd) return false;
  return as < bs + bd && bs < as + ad;
}

function hasConflict(start, duration, orders) {
  return (orders || []).some((o) => BUSY.includes(o.status) &&
    overlaps(start, duration, Number(o.appointmentTime || o.actualStartTime || 0), o.duration));
}

function findFreeSlot(fromTs, duration, orders, opts) {
  const step = Number((opts && opts.step) || STEP_MS);
  const maxSteps = Number((opts && opts.maxSteps) || 36);
  let t = Number(fromTs || 0);
  for (let i = 0; i < maxSteps; i++) {
    if (!hasConflict(t, duration, orders)) return t;
    t += step;
  }
  return null;
}

const endOf = (start, duration) => Number(start || 0) + Number(duration || 0);

module.exports = { STEP_MS, overlaps, hasConflict, findFreeSlot, endOf };
