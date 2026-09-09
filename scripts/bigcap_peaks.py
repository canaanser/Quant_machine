# -*- coding: utf-8 -*-
r"""大票池: 价格峰 × 筹码峰 分布统计（老板 2026-09-06）
对每只大票(市值≥300亿):
  - 逐日筹码分布 → 每日"最大筹码峰规模"(主峰≥50%峰高的连续区质量占比)
  - 波段顶(120日新高、后15日均值回落>3%确认) → 记录: 价格峰高度、主峰规模、主峰位置/现价
输出:
  1) 全池所有波段顶: 主峰规模分布 (发套上限在哪)
  2) 每票最高主峰规模(生长上限)分布
  3) 主峰规模分位 vs 后续30日(顶后回落)
"""
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import numpy as np
from core.data_loader.freestockdb import fetch_daily_qfq_single


def main_peak_size(chip, bins):
    """主峰规模: 密度最大点, ≥其50%高度连续区质量占比(%)"""
    pk = int(np.argmax(chip))
    if chip[pk] <= 0:
        return 0.0
    peak_val = chip[pk]
    left = pk
    while left > 0 and chip[left - 1] >= peak_val * 0.5:
        left -= 1
    right = pk
    while right < len(bins) - 1 and chip[right + 1] >= peak_val * 0.5:
        right += 1
    return float(chip[left:right + 1].sum() * 100)


def process(code):
    df = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
    if df is None or len(df) < 500:
        return [], []
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

    tops = []       # (date, px, main_peak%, peak_pos/px, fwd30_maxdd)
    peak_seq = []   # 每日主峰规模(限2024后省内存, 每10日存)
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
        if i % 10 == 0 and "20240101" <= d <= "20260903":
            peak_seq.append(main_peak_size(c, bins))
        if not ("20210101" <= d <= "20260801"):
            continue
        if i < 130 or i > n - 20:
            continue
        if ca[i] >= ca[i - 120:i].max() and ca[i + 1:i + 16].mean() < ca[i] * 0.97:
            mp = main_peak_size(c, bins)
            pk_idx = int(np.argmax(c))
            pos = bins[pk_idx] / p if p > 0 else 0.0
            # 顶后30日最大回撤
            fwd = ca[i + 1:i + 31]
            dd30 = (fwd.min() / p - 1) * 100 if len(fwd) else 0.0
            tops.append((d, round(float(p), 2), round(mp, 1), round(float(pos), 2), round(float(dd30), 1)))
    return tops, peak_seq


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    print(f"大票池 {len(big)} 只, 统计价格峰/筹码峰...", flush=True)
    all_tops = []
    all_peak_max = []
    all_peak_p99 = []
    all_daily_max = []
    t0 = time.time()
    for k, code in enumerate(big):
        tops, seq = process(code)
        all_tops.extend([(code,) + t for t in tops])
        if seq:
            all_daily_max.append((code, max(seq)))
            all_peak_max.append((code, max((t[2] for t in tops), default=0.0)))
            all_peak_p99.append((code, float(np.percentile([t[2] for t in tops], 99)) if tops else 0.0))
        if (k + 1) % 100 == 0:
            el = time.time() - t0
            print(f"  {k+1}/{len(big)} 顶{len(all_tops)} 耗时{el:.0f}s", flush=True)
    # 输出
    out = []
    out.append(f"\n===== 大票池 {len(big)}只 价格峰/筹码峰统计 =====")
    if all_tops:
        mp = np.array([t[3] for t in all_tops])
        px = np.array([t[2] for t in all_tops])
        dd = np.array([t[5] for t in all_tops])
        pos = np.array([t[4] for t in all_tops])
        out.append(f"\n确认波段顶 {len(all_tops)} 个:")
        out.append(f"主峰规模%: 中位{np.median(mp):.1f} P25{np.percentile(mp,25):.1f} "
                   f"P75{np.percentile(mp,75):.1f} P90{np.percentile(mp,90):.1f} P99{np.percentile(mp,99):.1f} 上限{mp.max():.1f}")
        out.append(f"主峰位置/顶价: 中位{np.median(pos):.2f}")
        out.append(f"顶后30日回撤: 中位{np.median(dd):.1f}%")
        # 主峰规模分档 → 后续回撤
        out.append("\n主峰规模分档 → 顶后30日回撤:")
        for lo, hi in [(0, 20), (20, 30), (30, 40), (40, 50), (50, 60), (60, 101)]:
            sel = dd[(mp >= lo) & (mp < hi)]
            if len(sel) >= 10:
                out.append(f"  主峰{lo}-{hi}%: {len(sel)}顶 30日回撤中位{np.median(sel):.1f}% 平均{sel.mean():.1f}%")
        # 每票生长上限
        out.append(f"\n每票最大主峰(生长上限) {len(all_peak_max)}只: "
                   f"中位{np.median([x[1] for x in all_peak_max]):.1f}% "
                   f"P90{np.percentile([x[1] for x in all_peak_max],90):.1f}% 上限{max(x[1] for x in all_peak_max):.1f}%")
        top5 = sorted(all_tops, key=lambda x: -x[3])[:8]
        out.append("\n主峰最大的8个波段顶: " + " | ".join(
            f"{t[0]}:{t[1]}@{t[2]}主峰{t[3]}%位{t[4]}" for t in top5))
    else:
        out.append("无波段顶样本")
    txt = "\n".join(out)
    print(txt, flush=True)
    open(str(PROJECT_ROOT / "outputs/bigcap_peaks.txt"), "w", encoding="utf-8").write(txt)
    return txt


if __name__ == "__main__":
    main()
