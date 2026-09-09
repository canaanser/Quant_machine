# -*- coding: utf-8 -*-
r"""无门版分年验证 (2026-09-07, 环境开关依据)
口径: 与 live_strategy_backtest 的 'none' 完全一致(纯筹码n=3买点 + 峰顶卖 + 防崩-12),
只多记录每笔交易(入场/出场/收益), 按【入场年份】归组:
  每年每股倍数 = Π(1+该股当年入场交易的收益)  [含持有到9/7未平的按现价算]
  每年几何 = 当年有交易的股票们的倍数的几何平均
输出: 每年 交易数/几何/胜率/中位收益 → 环境开关阈值参考
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


def sim(df):
    """跑无门逻辑, 返回该股全部已了结交易 [(entry_year, ret), ...] + 未平(按末日价)"""
    ca = df["close"].values
    la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    N = len(df)
    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    trades = []
    shares, entry_px, entry_i = 0.0, None, None
    hold_hi, hhd = 0.0, 0
    end_i = None
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
        if d > "20260907":
            break
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
                trades.append((entry_i, p / entry_px - 1))
                shares = 0.0; entry_px = None
                hold_hi = 0.0; hhd = 0
        else:
            trap = c[bins > p].sum() * 100
            bot = c[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if not (trap >= TRAP_MIN and BOT_LO <= bot <= BOT_HI):
                continue
            shares = 1.0 / p
            entry_px = p; entry_i = i
            hold_hi = p; hhd = 0
            end_i = i
    if shares > 1e-9 and end_i is not None:
        trades.append((end_i, ca[-1] / entry_px - 1))  # 未平, 按窗口末日价
    return trades


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    step = max(1, len(big) // 200)
    sample = big[::step][:200]
    print(f"分年验证: {len(sample)}只大票 无门版 2024-01~2026-09", flush=True)
    years = {}
    stk_year = {}
    for ci, c in enumerate(sample):
        df = fetch_daily_qfq_single(c, "2021-01-01", "2026-12-31")
        if df is None or len(df) <= 500:
            continue
        trs = sim(df)
        if not trs:
            continue
        for i, ret in trs:
            y = str(df.index[i].date())[:4]
            years.setdefault(y, []).append(ret)
            stk_year.setdefault(y, {}).setdefault(c, 1.0)
            stk_year[y][c] *= (1.0 + ret)
        if (ci + 1) % 50 == 0:
            print(f"  {ci+1}/{len(sample)}", flush=True)
    print(f"\n{'年份':<6}{'交易数':>6}{'股票数':>6}{'几何':>9}{'胜率':>7}{'中位':>8}")
    for y in sorted(years):
        rets = np.array(years[y])
        mult = np.array([v for v in stk_year[y].values()])
        geo = float(np.exp(np.mean(np.log(np.clip(mult, 1e-9, None)))))
        print(f"{y:<6}{len(rets):>6}{len(mult):>6}{geo:>8.3f}({(geo-1)*100:+5.0f}%)"
              f"{(rets > 0).mean()*100:>6.0f}%{np.median(rets)*100:>+7.1f}%", flush=True)
    print("\n(交易按入场年归组; 跨年持仓收益全计入场年; 含9/7未平仓按现价)")
    print("环境开关参考: 某年胜率<40% => 降半仓或空仓(2026即此情形), 别和筹码逻辑对着干")


if __name__ == "__main__":
    main()
