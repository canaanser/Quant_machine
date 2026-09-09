# -*- coding: utf-8 -*-
"""大票池快照(腾讯): 对本地已知 ≥300亿 的 630 只批量拍实时快照 → 跌深榜/涨多榜"""
import io, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from core.trade.rtfeed import fetch

MV = json.load(open(str(Path(__file__).parent.parent / "outputs/chip_mv_cache.json")))
big = sorted([c for c, v in MV.items() if v and v >= 300.0])
t0 = time.time()
quotes = {}
for i in range(0, len(big), 100):
    try:
        quotes.update(fetch(big[i:i + 100]))
    except Exception as e:
        print("块失败", e, flush=True)
rows = []
for c in big:
    q = quotes.get(c)
    if q:
        rows.append(dict(code=c, name=q["name"], px=q["px"], pct=q["pct"],
                         mv=MV[c] / 1e8))
rows.sort(key=lambda x: -x["mv"])
ts = time.strftime("%Y%m%d_%H%M%S")
out = Path(__file__).parent.parent / "Stream/snapshots"
json.dump(rows, open(str(out / f"snap_big_{ts}.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(f"快照完成 {ts}: {len(rows)}只 ≥300亿, 用时{time.time()-t0:.0f}s")
dn = sorted(rows, key=lambda x: x["pct"])[:30]
print(f"\n=== 今日跌最深 30 (≥300亿) ===")
for r in dn:
    print(f"{r['code']} {r['name']:<10}{r['px']:>8.2f} {r['pct']:>+6.2f}% {r['mv']:.0f}亿")
print(f"\n=== 今日涨最多 15 (≥300亿) ===")
for r in sorted(rows, key=lambda x: -x["pct"])[:15]:
    print(f"{r['code']} {r['name']:<10}{r['px']:>8.2f} {r['pct']:>+6.2f}% {r['mv']:.0f}亿")
print(f"\n分布: 涨{sum(1 for r in rows if r['pct']>0.05)} 跌{sum(1 for r in rows if r['pct']<-0.05)} "
      f"平{sum(1 for r in rows if abs(r['pct'])<=0.05)} | 平均{r['pct'] if False else round(sum(r['pct'] for r in rows)/len(rows),2)}%")
