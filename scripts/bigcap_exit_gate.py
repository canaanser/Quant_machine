# -*- coding: utf-8 -*-
"""严卡止盈验证: 用"坑深"反规律当离场闸门（老板 2026-09-06）
在确认波段顶模拟: 
  浅坑(<20%坑): 顶形成就走(动量衰竭,二次启动18%) → 收益≈0
  深坑(>40%坑): 拿着吃60日(二次启动47%) → 60日末收益
对比: 深坑拿住 vs 浅坑卖掉的60日实际收益分布, 看规律有没有钱赚
"""
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import numpy as np
from core.data_loader.freestockdb import fetch_daily_qfq_single


def process(code):
    df = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
    if df is None or len(df) < 500:
        return []
    ca = df["close"].values
    la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    dates = [d.strftime("%Y%m%d") for d in df.index]
    n = len(df)
    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    res = []
    for i in range(n):
        t = tv[i]
        if t > 0 and ha[i] > 0:
            tt = min(t / 100.0, 0.8)
            chip *= (1 - tt)
            m = (bins >= la[i] - 1e-9) & (bins <= ha[i] + 1e-9)
            if m.any():
                chip[m] += tt / m.sum()
        s = chip.sum()
        if s <= 0:
            continue
        c = chip / s
        p = ca[i]
        d = dates[i]
        if not ("20210101" <= d <= "20260601"):
            continue
        if i < 130 or i > n - 61:
            continue
        if ca[i] >= ca[i - 120:i].max() and ca[i + 1:i + 16].mean() < ca[i] * 0.97:
            pk = int(np.argmax(c))
            peak_val = c[pk]
            left = pk
            while left > 0 and c[left - 1] >= peak_val * 0.5:
                left -= 1
            right = pk
            while right < len(bins) - 1 and c[right + 1] >= peak_val * 0.5:
                right += 1
            mp = c[left:right + 1].sum() * 100
            w120 = ca[i - 120:i]
            pre_dd = (w120.min() / w120.max() - 1) * 100
            # 拿60日: 末价收益 + 期间最大浮盈
            f60 = ca[i + 1:i + 61]
            ret60 = (f60[-1] / p - 1) * 100 if len(f60) >= 55 else None
            mx60 = (f60.max() / p - 1) * 100 if len(f60) else None
            if ret60 is None:
                continue
            res.append((round(pre_dd, 1), round(mp, 1), round(ret60, 1), round(float(mx60), 1)))
    return res


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    print(f"大票池 {len(big)} 只...", flush=True)
    allr = []
    t0 = time.time()
    for k, code in enumerate(big):
        allr.extend(process(code))
        if (k + 1) % 150 == 0:
            print(f"  {k+1}/{len(big)} 顶{len(allr)} 耗时{time.time()-t0:.0f}s", flush=True)
    A = np.array(allr, dtype=float)
    deep = A[A[:, 0] <= -40]      # 深坑
    mid = A[(A[:, 0] > -40) & (A[:, 0] <= -20)]
    shallow = A[A[:, 0] > -20]    # 浅坑
    out = []
    out.append(f'\n===== 严卡止盈: 顶形成时[走还是拿] x 坑深 (波段顶 {len(A)}) =====')
    out.append(f"{'群':<12}{'顶数':>6}{'坑深':>7}{'主峰':>6}"
               f"{'| 拿60日收益中位':>15}{'60日最大浮盈':>12}{'| 若顶就走':>10}")
    for nm, s in [("深坑>40%", deep), ("中坑20-40", mid), ("浅坑<20%", shallow)]:
        r60 = np.median(s[:, 2]); mx = np.median(s[:, 3])
        win = np.mean(s[:, 2] > 0) * 100
        out.append(f"{nm:<12}{len(s):>6}{np.median(s[:,0]):>+6.0f}%{np.median(s[:,1]):>6.1f}%"
                   f"{r60:>+13.1f}%{mx:>+11.1f}%{'0(卖顶)':>10}  60日为正 {win:.0f}%")
    # 规则收益: 浅坑走(0), 中坑走(0), 深坑拿(60日收益) → 平均
    deep60 = deep[:, 2]
    out.append(f"\n[模拟: 浅/中坑顶即走(保住0), 深坑拿60日]")
    out.append(f"  深坑 {len(deep60)}个 拿60日: 平均{deep60.mean():+.1f}% 中位{np.median(deep60):+.1f}% "
               f"正{np.mean(deep60>0)*100:.0f}% | 全拿(A组对照): 全顶60日平均{A[:,2].mean():+.1f}%")
    out.append(f"  说明: 若'浅坑早走+深坑拿', 相对'所有顶都拿60日' 改善 = "
               f"{(deep60.mean())*0.41 + 0*0.59 - A[:,2].mean():+.1f}%(深坑占{len(deep60)/len(A)*100:.0f}%)")
    txt = "\n".join(out)
    print(txt, flush=True)
    open(str(PROJECT_ROOT / "outputs/bigcap_exit_gate.txt"), "w", encoding="utf-8").write(txt)


if __name__ == "__main__":
    main()
