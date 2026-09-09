# -*- coding: utf-8 -*-
r"""大市值行情快照 (2026-09-08, 老板方案: 把行情页数据源整页扒下来成静态)
爬取东财"沪深A股按总市值排序"的数据接口(网页自身的数据源), 一次多页拿全,
滤出 总市值≥300亿, 落成静态 JSON/TXT 快照 → 盘中"全市场大票"一眼看全。
用法(Windows): E:\python\python.exe -B scripts\market_snapshot.py [--min-mv 300]
输出: outputs/market_snapshot_YYYYMMDD_HHMMSS.json / .txt (列表+跌深榜+涨多榜)
"""
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
PROJECT_ROOT = Path(__file__).parent.parent

MV_MIN = 300.0  # 亿
FIELDS = "f12,f14,f2,f3,f20,f5,f6"
FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"  # 沪深京A股(主板/科创/创业)


def fetch_page(pn):
    url = ("https://push2.eastmoney.com/api/qt/clist/get?pn=%d&pz=100&po=1&np=1"
           "&fltt=2&invt=2&fid=f20&fs=%s&fields=%s" % (pn, urllib.parse.quote(FS), FIELDS))
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://quote.eastmoney.com/"})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read().decode("utf-8"))
    d = (j.get("data") or {})
    return d.get("diff") or [], d.get("total") or 0


def main():
    import urllib.parse
    args = sys.argv[1:]
    mv_min = MV_MIN
    for i, a in enumerate(args):
        if a == "--min-mv" and i + 1 < len(args):
            mv_min = float(args[i + 1])
    t0 = time.time()
    rows = []
    pn = 1
    total = 0
    while True:
        diff, total = fetch_page(pn)
        if not diff:
            break
        for it in diff:
            mv = (it.get("f20") or 0) / 1e8
            if mv < mv_min:
                rows.append(diff)  # 触发即停的标记(不进入)
                break
            rows.append(dict(code=it.get("f12"), name=it.get("f14"),
                             px=it.get("f2"), pct=it.get("f3"),
                             mv=round(mv, 1), vol=it.get("f5")))
        else:
            pn += 1
            if pn > 15:
                break
            continue
        break
    big = []
    for diff in rows:
        if isinstance(diff, list):
            continue
        big.append(diff)
    big.sort(key=lambda x: -x["mv"])
    ts = time.strftime("%Y%m%d_%H%M%S")
    base = PROJECT_ROOT / "outputs" / f"market_snapshot_{ts}"
    with open(str(base) + ".json", "w", encoding="utf-8") as f:
        json.dump(big, f, ensure_ascii=False)
    with open(str(base) + ".txt", "w", encoding="utf-8") as f:
        f.write(f"大市值快照 {ts} | ≥{mv_min:.0f}亿 {len(big)}只 | 全市场{total} (用时{time.time()-t0:.0f}s)\n")
        f.write(f"{'代码':<8}{'名称':<12}{'现价':>9}{'涨跌%':>8}{'总市值(亿)':>11}\n")
        for r in big:
            f.write(f"{r['code']:<8}{r['name']:<12}{r['px']:>9.2f}{r['pct']:>+7.2f}%{r['mv']:>10.0f}\n")
        # 跌深榜(可能的机会候选)与涨多榜
        dn = sorted(big, key=lambda x: x["pct"])[:25]
        up = sorted(big, key=lambda x: -x["pct"])[:15]
        f.write("\n=== 今日跌幅最深(≥300亿, 机会候选) ===\n")
        for r in dn:
            f.write(f"{r['code']} {r['name']} {r['px']:.2f} {r['pct']:+.2f}% {r['mv']:.0f}亿\n")
        f.write("\n=== 今日涨幅最大(≥300亿) ===\n")
        for r in up:
            f.write(f"{r['code']} {r['name']} {r['px']:.2f} {r['pct']:+.2f}% {r['mv']:.0f}亿\n")
    print(f"快照完成: {base}.txt ({len(big)}只 ≥{mv_min}亿, 全市场{total}, {time.time()-t0:.0f}s)")
    print(f"\n=== 今日跌幅最深 25 (≥300亿) ===")
    for r in dn:
        print(f"{r['code']} {r['name']:<10} {r['px']:>8.2f} {r['pct']:>+6.2f}% {r['mv']:.0f}亿")


if __name__ == "__main__":
    main()
