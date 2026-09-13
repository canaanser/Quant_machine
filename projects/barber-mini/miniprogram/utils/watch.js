// 实时订阅封装：只用 db.watch（契约：不引 WebSocket）。含**有上限**的重连与退订。
// ⚠️ 2026-09-14：原来无上限重连 —— 在没有实时通道的环境（模拟器/弱网）会无限刷
//   `websocket not connected` / `DISCONNECTED` 错误日志，把 console 淹掉。
//   现在最多重试 MAX_RETRY 次，之后**安静停下**（数据靠 onShow 时主动拉取兜底）。
const MAX_RETRY = 3;

export function watch(query, { onChange, onError, retryMs = 2000 } = {}) {
  let watcher = null, closed = false, timer = null, tries = 0;

  const start = () => {
    watcher = query.watch({
      onChange: (snap) => { tries = 0; if (onChange) onChange(snap); },
      onError: (err) => {
        if (onError) onError(err);
        if (closed || tries >= MAX_RETRY) {
          if (tries >= MAX_RETRY) console.warn("[watch] 实时通道不可用，已停止重连（改用主动拉取）");
          return;
        }
        tries += 1;
        clearTimeout(timer);
        timer = setTimeout(start, retryMs * tries);   // 退避：2s / 4s / 6s
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
