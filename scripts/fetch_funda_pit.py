# -*- coding: utf-8 -*-
"""PIT 财报指标抓取(后台, 能拿多少拿多少) — 200样本 indicator 表
每 code 拉 2024q1..2026q2 indicator(statDate), 记 pubDate/roe/毛利/净利率, 落 outputs/funda_pit_cache.json
在线接口(老板确认不烧额度), 逐票限速. 跑完打印覆盖数.
"""
import io, json, os, sys, time
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "3rdpart_pybao"))
import stock_sdk
stock_sdk.set_init("8.138.149.215:12328")
QUARTERS = ["2026q2", "2026q1", "2025q4", "2025q3", "2025q2", "2025q1",
            "2024q4", "2024q3", "2024q2", "2024q1"]
CACHE = ROOT / "outputs" / "funda_pit_cache.json"
codes = sys.argv[1:]
if not codes:
    mv = json.load(open(str(ROOT / "outputs/chip_mv_cache.json"), encoding='utf-8'))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    step = max(1, len(big) // 200)
    codes = big[::step][:200]

def suffix(code):
    return (code + ".XSHG") if code[0] in ("6", "9", "5") else code + ".XSHE"

cache = {}
if CACHE.exists():
    try: cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception: cache = {}
ok = fail = 0
t0 = time.time()
for code in codes:
    if code in cache:
        ok += 1; continue
    got = {}
    for q in QUARTERS:
        try:
            rows = stock_sdk.get_fundamentals(
                stock_sdk.query(stock_sdk.indicator).filter(
                    getattr(stock_sdk.indicator, "code") == suffix(code)),
                statDate=q)
            for r in (rows or []):
                d = dict(r)
                keep = {k: d.get(k) for k in ("code", "statDate", "pubDate", "roe",
                                              "gross_profit_margin", "net_profit_margin",
                                              "eps", "inc_revenue", "inc_net_profit")}
                got[q] = keep
                break
        except Exception:
            pass
        time.sleep(0.3)
    if got:
        cache[code] = got; ok += 1
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    else:
        fail += 1
    if (ok + fail) % 25 == 0:
        print(f"进度 {ok+fail}/{len(codes)} ok={ok} fail={fail} 用时{time.time()-t0:.0f}s", flush=True)
print(f"完成 ok={ok} fail={fail} 覆盖缓存 {len(cache)} | 用时{time.time()-t0:.0f}s")
