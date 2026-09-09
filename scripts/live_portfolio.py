# -*- coding: utf-8 -*-
r"""组合级验证 v2: 无门买点 + 峰顶卖 + 防崩, 多档K等权 (2026-09-07)
单票回测(几何1.57)是"每股各自满仓循环"的期望, 不等于真组合。
本脚本把200只的信号按日汇总成真组合账本:
  - 最多 K 个仓位, 每仓目标 = 当日净值/K (等权满仓型)
  - 卖出先于买入结算; 满仓/现金不足/已持该票 → 跳过(记 skipped)
  - 成交价 = 事件日收盘(T日收盘, 真实可执行)
  - 现金占用率 = 平均 (1 - cash/eq) —— 反映仓位纪律的"投出去多少"
对比 K=1..40: 看分散度对期末/回撤的影响, 并对照老板实际纪律(1-2只×20-30% ≈
小K+大量现金 → 用现金占用率把结果按比例折到老板的真实投入)。
注意: 全程换手次数随K增大而增大(K=1仅3-5笔), 小K结果=少数几次选名运气, 只做量级参考。
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
START, END = 20240101, 20260907


def gen_events(df):
    """单票事件链 [(date_int, is_buy, px), ...] — 无门逻辑, 与 live_strategy_backtest 'none' 一致"""
    ca = df["close"].values
    la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    N = len(df)
    dates = np.array([int(str(d.date()).replace("-", "")) for d in df.index])
    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    ev = []
    holding = False
    entry_px = 0.0
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
        d = dates[i]
        if not (START <= d <= END):
            continue
        if holding:
            if p > hold_hi:
                hold_hi = p; hhd = 0
            else:
                hhd += 1
            pnl = p / entry_px - 1
            sell = decide(entry_px, p, hold_hi, hhd) != "hold"
            if sell:
                ev.append((d, 0, p))
                holding = False
        else:
            trap = c[bins > p].sum() * 100
            bot = c[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if not (trap >= TRAP_MIN and BOT_LO <= bot <= BOT_HI):
                continue
            ev.append((d, 1, p))
            holding = True
            entry_px = p
            hold_hi = p; hhd = 0
    return ev, dates, ca


def run_portfolio(events_by_code, close_at, K, snaps):
    """K=最大并行仓数, 每仓 = 当日净值/K。返回 (final, snap_eq, stats)"""
    queue = []
    for code, evs in events_by_code.items():
        for d, buy, px in evs:
            queue.append((d, 1 if buy else 0, code, px))  # 同日卖(0)先于买(1)
    queue.sort()
    cash = 1.0
    pos = {}          # code -> (shares, cost_px)
    skipped = 0
    n_trades = 0
    closed_year = {}
    snap_i = 0
    snap_eq = []
    peak, maxdd = 1.0, 1.0
    cur_equity = 1.0
    inv_sum = 0.0     # 事件时投入比累计(近似时间加权, 事件密度≈交易频率)
    n_ev = 0
    for d, prio, code, px in queue:
        if prio == 0:  # 卖
            if code not in pos:
                continue
            sh, cp = pos.pop(code)
            cash += sh * px
            n_trades += 1
            y = str(d)[:4]
            closed_year.setdefault(y, []).append(px / cp - 1)
        else:          # 买
            if code in pos or len(pos) >= K or cash <= 0:
                skipped += 1
                continue
            alloc = min(cash, cur_equity / K)
            if alloc <= 0:
                skipped += 1
                continue
            sh = alloc / px
            cash -= alloc
            pos[code] = (sh, px)
        eq = cash + sum(sh * close_at[code](d) for code, (sh, _cp) in pos.items())
        cur_equity = eq
        inv_sum += 1.0 - cash / eq if eq > 0 else 0.0
        n_ev += 1
        while snap_i < len(snaps) and d >= snaps[snap_i]:
            snap_eq.append((snaps[snap_i], eq))
            snap_i += 1
        peak = max(peak, eq)
        maxdd = min(maxdd, eq / peak)
    eq = cash + sum(sh * close_at[code](END) for code, (sh, _cp) in pos.items())
    while snap_i < len(snaps):
        snap_eq.append((snaps[snap_i], eq))
        snap_i += 1
    wins = {y: float(np.mean(np.array(r) > 0)) for y, r in closed_year.items()}
    return eq, snap_eq, dict(trades=n_trades, skipped=skipped, maxdd=float(maxdd),
                             wins=wins, inv=inv_sum / max(n_ev, 1))


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    step = max(1, len(big) // 200)
    sample = big[::step][:200]
    print(f"组合验证: {len(sample)}只大票 2024-01~2026-09 | 多档K等权无门", flush=True)
    events_by_code, close_at = {}, {}
    for ci, c in enumerate(sample):
        df = fetch_daily_qfq_single(c, "2021-01-01", "2026-12-31")
        if df is None or len(df) <= 500:
            continue
        evs, dates, closes = gen_events(df)
        if not evs:
            continue
        events_by_code[c] = evs
        darr, carr = dates, closes
        def mk(darr=darr, carr=carr):
            def at(d):
                i = int(np.searchsorted(darr, d, side='right')) - 1
                return float(carr[max(i, 0)])
            return at
        close_at[c] = mk()
        if (ci + 1) % 50 == 0:
            print(f"  {ci+1}/{len(sample)}", flush=True)
    snaps = [20241231, 20251231, 20260907]
    print(f"有信号的票: {len(events_by_code)} 只", flush=True)
    print(f"\n{'K':<4}{'期末':>8}{'最大回撤':>9}{'换手':>5}{'错失':>6}{'投入比':>7}{'分年净值(绝对)'}", flush=True)
    for K in (1, 2, 3, 4, 6, 8, 12, 20, 40):
        eq, seq, st = run_portfolio(events_by_code, close_at, K, snaps)
        parts = " ".join(f"{str(s)[4:6]}/{str(s)[:4]}:{v:.2f}" for s, v in seq)
        print(f"K={K:<2}{eq:>8.3f}{(1-st['maxdd'])*100:>8.0f}%{st['trades']:>5}"
              f"{st['skipped']:>6}{st['inv']*100:>6.0f}%  {parts}", flush=True)
    print("\n注: 期末=绝对净值(1.0起)。换手=平仓笔数。错失=因满仓/现金不足跳过的买点。", flush=True)
    print("投入比≈平均仓位占用。老板纪律(1-2只×20-30%)≈K=2但投入比仅40-60%。", flush=True)


if __name__ == "__main__":
    main()
