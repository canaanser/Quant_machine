# -*- coding: utf-8 -*-
r"""实盘组合策略 v1 回测验证 (2026-09-07 独立基线, 重写干净版)
买点: 纯筹码n=3 套牢≥60 底5-20
卖点: 峰顶跟踪(盈30回落2%或滞涨15) + 防崩-12
对比三门: 无门 / 企稳门(不创新低) / 深度门(距120日高≤-30%/-40%)
"""
import json, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import numpy as np
from core.data_loader.freestockdb import fetch_daily_qfq_single

TRAP_MIN = 60.0
BOT_LO, BOT_HI = 5.0, 20.0
from core.risk.sellrules import decide


def _core(df, gate_mode):
    """gate_mode: 'none' / 'stable' / 'depth(-30)' / 'depth(-40)'"""
    ca = df["close"].values
    la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    N = len(df)
    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    cash, shares, entry_px = 1.0, 0.0, None
    hold_hi, hhd = 0.0, 0
    for i in range(N):
        t = tv[i]
        if t > 0 and ha[i] > 0:
            alpha = min(t / 100.0 * 3.0, 1.0)
            chip *= (1 - alpha)
            m = (bins >= la[i] - 1e-9) & (bins <= ha[i] + 1e-9)
            if m.any():
                chip[m] += alpha / m.sum()
        s = chip.sum()
        if s <= 0:
            continue
        c = chip / s
        p = ca[i]
        d = str(df.index[i].date()).replace("-", "")
        if not ("20240101" <= d <= "20260907"):
            continue
        if shares > 0:
            if p > hold_hi:
                hold_hi = p; hhd = 0
            else:
                hhd += 1
            pnl = p / entry_px - 1
            sell = decide(entry_px, p, hold_hi, hhd) != "hold"
            if sell:
                cash += shares * p
                shares = 0.0; entry_px = None
                hold_hi = 0.0; hhd = 0
        else:
            trap = c[bins > p].sum() * 100
            bot = c[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if not (trap >= TRAP_MIN and BOT_LO <= bot <= BOT_HI):
                continue
            if gate_mode == 'stable' and i >= 25:
                if ca[i-4:i+1].min() < ca[i-24:i-4].min():
                    continue
            elif gate_mode.startswith('depth') and i >= 120:
                hi120 = ca[i-120:i+1].max()
                limit = -30 if gate_mode == 'depth(-30)' else -40
                if (p / hi120 - 1) * 100 > limit:
                    continue
            shares = cash / p
            cash = 0.0
            entry_px = p
            hold_hi = p; hhd = 0
    if shares > 1e-9 and N > 0:
        cash += shares * ca[-1]
    return cash


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    step = max(1, len(big) // 200)
    sample = big[::step][:200]
    print(f"回测: {len(sample)}只大票 2024-01~2026-09", flush=True)
    dfs = {}
    for ci, c in enumerate(sample):
        df = fetch_daily_qfq_single(c, "2021-01-01", "2026-12-31")
        if df is not None and len(df) > 500:
            dfs[c] = df
    for gm, nm in [("none", "无门"), ("stable", "企稳门"),
                   ("depth(-30)", "深度门≤-30%"), ("depth(-40)", "深度门≤-40%")]:
        navs = []
        for c, df in dfs.items():
            navs.append(_core(df, gm))
        g = np.array(navs, dtype=float)
        geo = float(np.exp(np.mean(np.log(np.clip(g, 1e-9, None)))))
        print(f"[{nm}] 几何{geo:.3f}({(geo-1)*100:+.0f}%) 中位{np.median(g):.2f} "
              f"盈利{(g>1).mean()*100:.0f}% P90{np.percentile(g,90):.2f}", flush=True)


if __name__ == "__main__":
    main()
