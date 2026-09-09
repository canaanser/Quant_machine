# -*- coding: utf-8 -*-
"""峰顶跟踪止盈 参数粗扫（不过拟合, 只找方向）2026-09-06
采样200只大票(市值分层抽), P模式参数网格:
  pnl_min {0.20,0.30,0.40} × retreat {0.98,0.95} × stall_days {10,15,20} → 简化为 9 组重点
对照组: M机械(盈10走)
"""
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import numpy as np
from bigcap_exit_peak import sim_one
from core.data_loader.freestockdb import fetch_daily_qfq_single


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    # 分层采样200: 市值从大到小每3只取1 → 覆盖各档
    step = max(1, len(big) // 200)
    sample = big[::step][:200]
    print(f"采样 {len(sample)} 只大票(市值≥300亿) | 2024-01~2026-09", flush=True)

    # 预拉数据一次, 各参数共享
    dfs = {}
    t0 = time.time()
    for k, code in enumerate(sample):
        dfs[code] = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
        if (k + 1) % 50 == 0:
            print(f"  拉数 {k+1}/{len(sample)} 耗时{time.time()-t0:.0f}s", flush=True)

    grid = [(0.20, 0.98, 15), (0.30, 0.98, 15), (0.40, 0.98, 15),
            (0.30, 0.95, 15), (0.30, 0.98, 10), (0.30, 0.98, 20),
            (0.20, 0.95, 20), (0.40, 0.95, 20)]
    print(f"\n{'参数(门槛/回落/滞涨)':<26}{'几何均':>9}{'中位':>7}{'盈利':>7}{'P10':>6}{'P90':>6}")
    # M 基线
    res_m = []
    for code in sample:
        df = dfs[code]
        if df is None or len(df) < 500:
            continue
        nav, _ = sim_one(df, 'M')
        res_m.append(nav)
    gm = np.array(res_m)
    print(f"M机械(盈10走)            : {float(np.exp(np.mean(np.log(np.clip(gm,1e-9,None))))):6.3f}"
          f"{np.median(gm):7.2f}{np.mean(gm>1)*100:6.0f}%"
          f"{np.percentile(gm,10):6.2f}{np.percentile(gm,90):6.2f}", flush=True)
    for pm, rt, sd in grid:
        res_p = []
        for code in sample:
            df = dfs[code]
            if df is None or len(df) < 500:
                continue
            nav, _ = sim_one(df, 'P', pnl_min=pm, retreat=rt, stall_days=sd)
            res_p.append(nav)
        g = np.array(res_p)
        geo = float(np.exp(np.mean(np.log(np.clip(g, 1e-9, None)))))
        print(f"P(盈{pm:.0%}/回落{1-rt:.0%}/滞涨{sd}d) : {geo:6.3f}"
              f"{np.median(g):7.2f}{np.mean(g>1)*100:6.0f}%"
              f"{np.percentile(g,10):6.2f}{np.percentile(g,90):6.2f}", flush=True)


if __name__ == "__main__":
    main()
