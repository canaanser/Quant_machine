# -*- coding: utf-8 -*-
"""筹码算法参数反演: 用老板首创证券两组精确数据校准
参考点(老板软件=通达信/东财筹码分布):
  601136 2026-09-04: 平均成本15.39 集中度13.25% 获利62.2%
  601136 2026-08-17: 平均成本15.81 集中度16.32% 获利23.34%(老板转述)
算法(通达信): 当日 = 摊量(换手率*n) + 昨日*(1-换手率*n)
摊量分布: 平均(均匀low-high) / 三角形(在low,high,(low+high)/2 三角分布)
扫参数 n∈{0.5,1,1.5,2,3,5} × 分布{平均,三角}, 看哪组最贴近两个参考日
"""
import sys
import numpy as np
from pathlib import Path

ROOT = Path("/mnt/e/stockgate/Quant_Alpha_System")
sys.path.insert(0, str(ROOT))
from core.data_loader.freestockdb import fetch_daily_qfq_single


def chip_params(df, n_coef, dist, start_days=400, full=False):
    """按通达信公式滚动筹码; 返回当日bins/chip"""
    la = df["low"].values; ha = df["high"].values
    cl = df["close"].values; tv = df["turnover"].values
    N = len(df)
    hi_all = float(ha.max())
    # bins 覆盖全历史价格范围, 分辨率 0.01元? 首创价格~10-30, 用0.02
    step = 0.02
    bins = np.arange(0, hi_all * 1.05 + step, step)
    chip = np.zeros(len(bins))
    for i in range(N):
        t = tv[i]
        if t > 0 and ha[i] > 0:
            alpha = min(t / 100.0 * n_coef, 1.0)  # 换手率×衰减系数
            chip *= (1 - alpha)
            lo_i, hi_i = la[i], ha[i]
            m = (bins >= lo_i) & (bins <= hi_i)
            if m.sum() == 0:
                # 极窄区间
                j = int(np.clip(np.searchsorted(bins, cl[i]), 0, len(bins) - 1))
                chip[j] += alpha
                continue
            if dist == "avg":
                chip[m] += alpha / m.sum()
            else:
                # 三角形: 顶点在 (lo+hi)/2? 通达信"最高最低平均价"三角 = 峰在均价
                avg_p = cl[i]
                x = bins[m]
                # 三角: lo->avg 升, avg->hi 降
                tri = np.where(x <= avg_p, (x - lo_i) / max(avg_p - lo_i, 1e-9),
                               (hi_i - x) / max(hi_i - avg_p, 1e-9))
                tri = np.clip(tri, 0, None)
                tri = tri / (tri.sum() + 1e-12)
                chip[m] += alpha * tri
    return bins, chip / (chip.sum() + 1e-12)


def metrics(bins, chip, px):
    c = chip / (chip.sum() + 1e-12)
    gain = c[bins < px].sum() * 100
    cum = np.cumsum(c)
    med = bins[np.searchsorted(cum, 0.5)]
    lo5 = bins[np.searchsorted(cum, 0.05)]
    hi95 = bins[np.searchsorted(cum, 0.95)]
    conc = (hi95 - lo5) / (hi95 + lo5) * 100
    # 平均成本=50%线
    return med, conc, gain



def main():
    import pandas as pd
    df = fetch_daily_qfq_single("601136", "2022-01-01", "2026-09-05")
    if df is None or len(df) < 200:
        print("no data"); return
    targets = [
        ("2026-09-04", 15.39, 13.25, 62.2),
        ("2026-08-24", 15.63, 15.67, 3.3),
        ("2026-08-17", 15.81, 16.32, 23.34),
        ("2026-07-22", 16.99, 17.89, 12.57),
    ]
    idx = {}
    for d, *_ in targets:
        hits = np.where(np.array([str(x.date()) for x in df.index]) == d)[0]
        idx[d] = int(hits[0]) if len(hits) else None
    for d, mc, cc, gc in targets:
        print(f"参考日 {d}: 目标[成本{mc} 集中{cc}% 获利{gc}%] 当日收盘{df['close'].values[idx[d]]:.2f}")
    print()
    results = []
    for n in [0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0]:
        for dist in ["avg", "tri"]:
            outs = []
            errs = []
            for d, mc, cc, gc in targets:
                i = idx[d]
                sub = df.iloc[:i + 1]
                bins, chip = chip_params(sub, n, dist)
                px = df["close"].values[i]
                med, conc, gain = metrics(bins, chip, px)
                err = abs(med - mc) / mc + abs(conc - cc) / cc + abs(gain - gc) / gc
                errs.append(err)
                outs.append((round(med, 2), round(conc, 2), round(gain, 1)))
            results.append((float(np.mean(errs)), n, dist, outs))
    for e, n, dist, outs in sorted(results):
        print(f"n={n:<4} {dist:<4} 误差{e:.3f} | " +
              " ".join(f"[成{o[0]} 集{o[1]}% 获{o[2]}%]" for o in outs))
    best = min(results)
    print(f"\n最佳: n={best[1]} 分布={best[2]} 误差{best[0]:.3f} -> {best[3]}")


if __name__ == "__main__":
    main()
