# -*- coding: utf-8 -*-
"""主峰规模 vs 顶前跌幅/涨幅结构（老板 2026-09-06 追问）
对每只大票的确认波段顶, 度量"这座山前面的坑":
  - pre_dd: 顶往前120日内最大回撤深度%(山脚下坑多深)
  - rally:  顶价 / 近120日最低 - 1 (从坑底爬升多少)
  - rise_days: 坑底到顶的天数
统计主峰规模分档 与 pre_dd/rally 的关系 → 主峰是不是坑里长出来的
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
        if not ("20210101" <= d <= "20260801"):
            continue
        if i < 130 or i > n - 20:
            continue
        if ca[i] >= ca[i - 120:i].max() and ca[i + 1:i + 16].mean() < ca[i] * 0.97:
            # 主峰规模
            pk = int(np.argmax(c))
            peak_val = c[pk]
            left = pk
            while left > 0 and c[left - 1] >= peak_val * 0.5:
                left -= 1
            right = pk
            while right < len(bins) - 1 and c[right + 1] >= peak_val * 0.5:
                right += 1
            mp = c[left:right + 1].sum() * 100
            # 前面的坑: 顶前120日最高→最低回撤深度 & 低点位置
            w120 = ca[i - 120:i]
            hi120 = w120.max()
            lo120 = w120.min()
            pre_dd = (lo120 / hi120 - 1) * 100        # 坑深(负)
            rally = (p / lo120 - 1) * 100             # 坑底爬升
            lo_day = i - 120 + int(np.argmin(w120))   # 坑底在顶前第几天
            days_up = i - lo_day                       # 坑底到顶天数
            # 坑底后涨幅 = rally
            res.append((d, round(mp, 1), round(pre_dd, 1), round(rally, 1), days_up, round(float(p), 2)))
    return res


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    print(f"大票池 {len(big)} 只...", flush=True)
    allr = []
    t0 = time.time()
    for k, code in enumerate(big):
        r = process(code)
        allr.extend([(code,) + t for t in r])
        if (k + 1) % 150 == 0:
            print(f"  {k+1}/{len(big)} 顶{len(allr)} 耗时{time.time()-t0:.0f}s", flush=True)
    A = np.array([[t[2], t[3], t[4]] for t in allr], dtype=float)  # mp, predd, rally
    mp = A[:, 0]; dd = A[:, 1]; rally = A[:, 2]
    import numpy as _np
    # allr = (code, d, mp, pre_dd, rally, days_up, px)
    allr_arr = _np.array([[t[2], t[3], t[4], t[5]] for t in allr], dtype=float)
    out = []
    out.append(f"\n===== 主峰规模 vs 前面的坑 (波段顶 {len(allr)} 个) =====")
    # 主峰分档 → 前面的坑
    out.append("\n[主峰规模分档 → 顶前120日回撤深度/坑底爬升]")
    out.append(f"{'主峰%':<12}{'顶数':>6}{'坑深中位':>10}{'坑底爬升中位':>12}{'坑底→顶天':>10}")
    for lo, hi in [(0, 20), (20, 30), (30, 40), (40, 50), (50, 60), (60, 101)]:
        sel = allr_arr[(mp >= lo) & (mp < hi)]
        if len(sel) < 20:
            continue
        s_dd = sel[:, 1]; s_ra = sel[:, 2]; s_dy = sel[:, 3]
        out.append(f"{lo}-{hi}%  {len(sel):>6}{np.median(s_dd):>+9.1f}%{np.median(s_ra):>+11.1f}%{np.median(s_dy):>10.0f}")
    # 反过来: 坑深分档 → 主峰
    out.append("\n[顶前坑深分档 → 主峰规模]")
    for lo, hi in [(-101, -40), (-40, -30), (-30, -20), (-20, -10), (-10, 0)]:
        sel = allr_arr[(dd >= lo) & (dd < hi)]
        if len(sel) < 20:
            continue
        s_mp = sel[:, 0]
        out.append(f"坑{lo}~{hi}%: {len(sel)}顶 主峰中位{np.median(s_mp):.1f}% P75{np.percentile(s_mp,75):.1f}%")
    # 相关系数
    corr_dd = np.corrcoef(mp, dd)[0, 1]
    corr_ra = np.corrcoef(mp, rally)[0, 1]
    out.append(f"\n相关性: 主峰规模 × 坑深 corr={corr_dd:+.3f} | × 坑底爬升 corr={corr_ra:+.3f}")
    txt = "\n".join(out)
    print(txt, flush=True)
    open(str(PROJECT_ROOT / "outputs/bigcap_pit_peak.txt"), "w", encoding="utf-8").write(txt)


if __name__ == "__main__":
    main()
