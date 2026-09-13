// 实时订阅封装：只用 db.watch（契约：不引 WebSocket）。含断线重连与退订。
export function watch(query, { onChange, onError, retryMs = 2000 } = {}) {
  let watcher = null, closed = false, timer = null;

  const start = () => {
    watcher = query.watch({
      onChange: (snap) => onChange && onChange(snap),
      onError: (err) => {
        if (onError) onError(err);
        if (!closed) { clearTimeout(timer); timer = setTimeout(start, retryMs); }  // 断线自动重连
      },
    });
  };
  start();
  return () => { closed = true; clearTimeout(timer); if (watcher) watcher.close(); };
}

export function watchBarber(db, barberId, cb) {
  return watch(db.collection("barbers").where({ _id: barberId }), { onChange: (s) => cb(s.docs[0] || null) });
}

export function watchMyOrders(db, barberId, cb) {
  return watch(db.collection("orders").where({ barberId }), { onChange: (s) => cb(s.docs || []) });
}
