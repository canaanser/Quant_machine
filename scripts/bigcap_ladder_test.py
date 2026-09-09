# -*- coding: utf-8 -*-
"""大票池(市值>300亿) 纯筹码买入 + 止盈梯度卖出 批量测试
买点: 套牢≥trap(默认0.60) 且 5%≤底部≤20%   (纯筹码两维)
卖点: 梯10/20/35 + 防崩-12%
2024-01-01 ~ 2026-09-03
用法(Windows权威): python -B scripts/bigcap_ladder_test.py [--out outputs/bigcap_ladder.txt]
"""
import sys
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import numpy as np
from chip_ladder_sell import simulate
from core.data_loader.freestockdb import fetch_daily_qfq_single


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--mv-cache", default="/tmp/chip_mv_cache.json")
    ap.add_argument("--trap", type=float, default=0.60)
    ap.add_argument("--mv-min", type=float, default=300.0, help="市值下限(亿)")
    ap.add_argument("--start", default="2024-01-01")
    args = ap.parse_args()

    mv = json.load(open(args.mv_cache))
    big = sorted([(c, v) for c, v in mv.items() if v and v >= args.mv_min],
                 key=lambda x: -x[1])
    print(f"池: 市值≥{args.mv_min:.0f}亿 → {len(big)}只 | 纯筹码买(套牢≥{args.trap:.0%},底5-20) "
          f"| 卖: 梯10/20/35+防崩12 | {args.start}~2026-09", flush=True)

    LAD = [(0.10, 1 / 3), (0.20, 0.5), (0.35, 1.0)]
    navs, ntr, fails = [], [], 0
    rows = []
    t0 = time.time()
    for i, (code, _mv) in enumerate(big):
        try:
            df = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
            if df is None or len(df) < 400:
                continue
            nav, tr = simulate(df, args.trap, LAD)
        except Exception:
            fails += 1
            continue
        navs.append(nav); ntr.append(len(tr))
        rows.append((code, round(nav, 3), len(tr)))
        if (i + 1) % 100 == 0:
            el = time.time() - t0
            print(f"  进度 {i+1}/{len(big)} 中位净 {np.median(navs):.2f} 耗时{el:.0f}s", flush=True)
    g = np.array(navs, dtype=float)
    geo = float(np.exp(np.mean(np.log(np.clip(g, 1e-9, None)))))
    out = []
    out.append(f"\n===== 大票池 {len(g)}只 纯筹码+梯10/20/35 =====")
    out.append(f"几何均 {geo:.3f} ({(geo-1)*100:+.1f}%) | 算术均 {g.mean():.2f} | "
               f"中位 {np.median(g):.2f} | 盈利票 {(g>1).mean()*100:.0f}% | "
               f"平均卖{np.mean(ntr):.0f}次/票")
    out.append(f"P10 {np.percentile(g,10):.2f} | P25 {np.percentile(g,25):.2f} | "
               f"P75 {np.percentile(g,75):.2f} | P90 {np.percentile(g,90):.2f}")
    rows.sort(key=lambda x: -x[1])
    out.append("Top10: " + " ".join(f"{c}:{n:.2f}" for c, n, _ in rows[:10]))
    out.append("Bot5:  " + " ".join(f"{c}:{n:.2f}" for c, n, _ in rows[-5:]))
    txt = "\n".join(out)
    print(txt, flush=True)
    json.dump(rows, open(str(PROJECT_ROOT / "outputs/bigcap_ladder.json"), "w"), ensure_ascii=False)
    return txt


if __name__ == "__main__":
    main()
