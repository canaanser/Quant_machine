# -*- coding: utf-8 -*-
"""峰顶跟踪止盈 vs 机械梯度（老板 2026-09-06: 用反规律跟踪峰顶, 到顶就走/提前走）
买点(纯筹码): 套牢≥60% 且 5%≤底部≤20%
卖点对比:
  M机械:   梯10/20/35 + 防崩-12%
  P峰顶:   持仓中跟踪主峰爬升, 现价逼近持有期新高且主峰已爬到现价附近 → 清仓; 防崩-12%
           提前档: 主峰位置≥现价×0.90 且 价格近3日不再创新高 → 走(不等到真顶)
2024-01-01~2026-09-03, 大票池(市值≥300亿)
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


def sim_one(df, sell_mode, pnl_min=0.30, retreat=0.98, stall_days=15):
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

    cash, shares, entry_px, entry_d = 1.0, 0.0, None, None
    hold_hi = 0.0          # 持有期最高收盘
    hold_hi_days = 0       # 距持有期新高的天数
    trades = []
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
        if not ("20240101" <= d <= "20260903"):
            continue
        if shares > 0:
            # 更新持有期最高
            if p > hold_hi:
                hold_hi = p
                hold_hi_days = 0
            else:
                hold_hi_days += 1
            pnl = p / entry_px - 1
            sell = False
            reason = ''
            if pnl <= -0.12:
                sell, reason = True, '防崩'
            elif sell_mode == 'M':
                # 机械梯度 10/20/35
                if pnl >= 0.10:
                    # 简化一档到就走(与梯度可比: 用10%止盈)
                    sell, reason = True, '盈10'
            elif sell_mode == 'P':
                # 峰顶跟踪: 涨幅≥pnl_min 后, 高位滞涨/峰顶回落才走
                if pnl >= pnl_min:
                    pk = int(np.argmax(c))
                    peak_pos = bins[pk] / p if p > 0 else 0
                    if hold_hi_days >= stall_days:
                        sell, reason = True, f'高位滞涨{hold_hi_days}日'
                    elif hold_hi > 0 and p < hold_hi * retreat and hold_hi_days >= 5:
                        sell, reason = True, f'峰顶回落'
            if sell:
                cash += shares * p
                trades.append((p / entry_px - 1) * 100)
                shares = 0.0
                entry_px = None
                hold_hi = 0.0; hold_hi_days = 0
        else:
            cnorm = chip / s
            trap = cnorm[bins > p].sum() * 100
            bot5 = cnorm[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if trap >= 60 and 5 <= bot5 <= 20:
                shares = cash / p
                cash = 0.0
                entry_px = p
                entry_d = d
                hold_hi = p
                hold_hi_days = 0
    if shares > 1e-9 and n > 0:
        cash += shares * ca[-1]
    return cash, trades


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    # 为控制时长先用全池(单票~0.15s x 627 ≈ 2min)
    print(f"大票池 {len(big)} 只: 机械梯度 vs 峰顶跟踪止盈 | 2024-01~2026-09", flush=True)
    res = {"M": [], "P": []}
    t0 = time.time()
    for k, code in enumerate(big):
        df = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
        if df is None or len(df) < 500:
            continue
        for m in ("M", "P"):
            nav, tr = sim_one(df, m)
            res[m].append(nav)
        if (k + 1) % 100 == 0:
            print(f"  {k+1}/{len(big)} 耗时{time.time()-t0:.0f}s", flush=True)
    out = []
    out.append(f"\n===== 大票池 {len(res['M'])}只: 机械梯度(M) vs 峰顶跟踪(P) =====")
    for m, nm in [("M", "M机械(盈10走)"), ("P", "P峰顶跟踪")]:
        g = np.array(res[m], dtype=float)
        geo = float(np.exp(np.mean(np.log(np.clip(g, 1e-9, None)))))
        out.append(f"[{nm}] 几何均 {geo:.3f} ({(geo-1)*100:+.1f}%) | 中位 {np.median(g):.2f} "
                   f"| 盈利 {(g > 1).mean()*100:.0f}% | P10 {np.percentile(g,10):.2f} P90 {np.percentile(g,90):.2f}")
    txt = "\n".join(out)
    print(txt, flush=True)
    open(str(PROJECT_ROOT / "outputs/bigcap_exit_peak.txt"), "w", encoding="utf-8").write(txt)


if __name__ == "__main__":
    main()
