# -*- coding: utf-8 -*-
"""PIT 财报批量抓取(分批 in_) — indicator 表 200样本×10期
保留已有缓存; 10只/批×10期 → 约200次调用, 几分钟。
"""
import io, json, sys, time
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "3rdpart_pybao"))
import stock_sdk
stock_sdk.set_init("8.138.149.215:12328")
QUARTERS = ["2026q2","2026q1","2025q4","2025q3","2025q2","2025q1","2024q4","2024q3","2024q2","2024q1"]
CACHE = ROOT / "outputs" / "funda_pit_cache.json"
mv = json.load(open(str(ROOT / "outputs/chip_mv_cache.json"), encoding='utf-8'))
big = sorted([c for c, v in mv.items() if v and v >= 300.0])
step = max(1, len(big) // 200)
codes = big[::step][:200]
def suffix(code):
    return (code + ".XSHG") if code[0] in ("6", "9", "5") else code + ".XSHE"
cache = {}
if CACHE.exists():
    try: cache = json.load(open(CACHE, encoding='utf-8'))
    except Exception: cache = {}
todo = [c for c in codes if c not in cache]
print(f"待抓 {len(todo)} 只, 已有 {len(cache)}", flush=True)
t0 = time.time(); done = 0
KEEP = ("code", "statDate", "pubDate", "roe", "net_profit_margin", "eps")
for bi in range(0, len(todo), 10):
    batch = todo[bi:bi+10]
    got_batch = {c: {} for c in batch}
    for q in QUARTERS:
        try:
            rows = stock_sdk.get_fundamentals(
                stock_sdk.query(stock_sdk.indicator).filter(
                    stock_sdk.indicator.code.in_([suffix(c) for c in batch])),
                statDate=q)
            for r in (rows or []):
                d = dict(r)
                c6 = str(d.get("code") or "")[-6:]
                got_batch.get(c6, {})[q] = {k: d.get(k) for k in KEEP}
        except Exception as e:
            pass
        time.sleep(0.4)
    for c in batch:
        if got_batch[c]:
            cache[c] = got_batch[c]
    json.dump(cache, open(CACHE, "w", encoding='utf-8'), ensure_ascii=False)
    done += len(batch)
    if done % 40 == 0 or bi + 10 >= len(todo):
        print(f"进度 {done}/{len(todo)} 缓存{len(cache)} 用时{time.time()-t0:.0f}s", flush=True)
print(f"完成 缓存{len(cache)} 用时{time.time()-t0:.0f}s")
