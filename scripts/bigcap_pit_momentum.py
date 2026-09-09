# -*- coding: utf-8 -*-
"""利用反规律: 前面的坑(动量)分群 → 顶后行为差异（老板 2026-09-06）
动量解释: 坑深=前期杀跌动量强(筹码砸散,主峰长不大)=动能未尽;
          坑浅=高位换手堆大山=动量衰竭。验证:
  分群: 按顶前120日坑深(深>40 / 中20-40 / 浅<20)
  看  : ① 顶后30/60日回撤 ② 顶后回调≥12%后60日内能否再创新高(二次启动率)
       ③ 主峰大小(复核反规律)
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
        if i < 130 or i > n - 80:
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
            hi120 = w120.max(); lo120 = w120.min()
            pre_dd = (lo120 / hi120 - 1) * 100
            # 顶后30/60日最大回撤
            f30 = ca[i + 1:i + 31]
            f60 = ca[i + 1:i + 61]
            dd30 = (f30.min() / p - 1) * 100 if len(f30) else None
            dd60 = (f60.min() / p - 1) * 100 if len(f60) else None
            # 回调≥12%后60日内再创新高?
            bounce = 0
            for j in range(i + 1, min(i + 91, n - 30)):
                if ca[j] / p - 1 <= -0.12:
                    after = ca[j + 1:min(j + 61, n)]
                    if len(after) and after.max() >= p:
                        bounce = 1
                    break
            res.append((round(pre_dd, 1), round(mp, 1), dd30, dd60, bounce))
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
    A = np.array([r for r in allr if r[2] is not None and r[3] is not None], dtype=float)
    out = []
    out.append(f"\n===== 前面的坑(动量)分群 → 顶后行为 (波段顶 {len(A)} 个) =====")
    out.append(f"{'群':<16}{'顶数':>6}{'坑深':>7}{'主峰':>6}{'30日回撤':>9}{'60日回撤':>9}{'回调后创新高':>10}")
    for nm, lo, hi in [("深坑(>40%)", 40, 101), ("中坑(20-40)", 20, 40), ("浅坑(<20%)", -101, 20)]:
        sel = A[(A[:, 0] >= -hi) & (A[:, 0] < -lo)] if nm != "浅坑(<20%)" else A[A[:, 0] > -20]
        if len(sel) < 30:
            continue
        mp = np.median(sel[:, 1])
        dd30 = np.median(sel[:, 2]); dd60 = np.median(sel[:, 3])
        bounce = np.mean(sel[:, 4]) * 100
        out.append(f"{nm:<16}{len(sel):>6}{np.median(sel[:,0]):>+6.0f}%{mp:>6.1f}%"
                   f"{dd30:>+8.1f}%{dd60:>+8.1f}%{bounce:>9.0f}%")
    # 二次启动只对有回调事件的
    out.append("\n[回调≥12%后60日再创新高 = 二次启动] 按坑深:")
    for nm, lo, hi in [("深坑(>40%)", 40, 101), ("中坑(20-40)", 20, 40), ("浅坑(<20%)", -101, 20)]:
        sel = A[(A[:, 0] >= -hi) & (A[:, 0] < -lo)] if nm != "浅坑(<20%)" else A[A[:, 0] > -20]
        sel = sel[sel[:, 4] >= 0]  # 有回调事件的
        if len(sel) < 20:
            continue
        out.append(f"  {nm}: 回调顶{len(sel)}个, 再创新高 {np.mean(sel[:,4])*100:.0f}%")
    txt = "\n".join(out)
    print(txt, flush=True)
    open(str(PROJECT_ROOT / "outputs/bigcap_pit_momentum.txt"), "w", encoding="utf-8").write(txt)


if __name__ == "__main__":
    main()
