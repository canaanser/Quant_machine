# -*- coding: utf-8 -*-
"""滚动汰换测试 v0.1 (2026-09-09) — 抄底池"汰弱换强" vs "抱着不动"
模型: 最多 K=8 席; 每席开仓 = 当日净值×1/8; 满员时新买点排队。
  mode=hold : 抱到卖点(防崩/峰顶/滞涨) 才出 —— 对照(接近组合验证K=8)
  mode=swap : 满员遇新买点: 若新信号5日涨幅 明显强于 持仓最弱(5日跌) 且最弱未破防崩 → 卖弱换新(汰弱留强)
用法: E:\\python\\python.exe -B scripts\\pool_swap_test.py [hold|swap] > outputs\\pool_swap_<m>.txt
"""
import io, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from core.data_loader.freestockdb import fetch_daily_qfq_single

TRAP_MIN, BOT_LO, BOT_HI = 60.0, 5.0, 20.0
START, END = 20240101, 20260907
K = 8
RET5_WIN = 5
SWAP_EDGE = 2.0   # 新信号近5日涨幅需比最弱持仓至少高2个点(百分点)才换


def gen(df):
    ca, la, ha, tv = df["close"].values, df["low"].values, df["high"].values, df["turnover"].values
    dates = np.array([int(str(d.date()).replace("-", "")) for d in df.index])
    N = len(df)
    hi_max = float(ha.max()); w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1; bins = np.arange(nb) * w
    chip = np.zeros(nb)
    evs = []           # (d, is_buy, px)
    holding = False; entry_px = 0.0; hold_hi, hhd = 0.0, 0
    for i in range(N):
        t = tv[i]
        if t > 0 and ha[i] > 0:
            a = min(t / 100.0 * 3.0, 1.0); chip *= (1 - a)
            m = (bins >= la[i] - 1e-9) & (bins <= ha[i] + 1e-9)
            if m.any(): chip[m] += a / m.sum()
        s = chip.sum()
        if s <= 0: continue
        c = chip / s; p = ca[i]; d = dates[i]
        if not (START <= d <= END): continue
        if holding:
            if p > hold_hi: hold_hi, hhd = p, 0
            else: hhd += 1
            pnl = p / entry_px - 1
            sell = False
            if pnl <= -0.12: sell = True
            elif pnl >= 0.30:
                if hhd >= 15: sell = True
                elif p < hold_hi * 0.98 and hhd >= 5: sell = True
            if sell:
                evs.append((d, 0, p)); holding = False
        else:
            trap = c[bins > p].sum() * 100
            bot = c[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
            if trap >= TRAP_MIN and BOT_LO <= bot <= BOT_HI:
                evs.append((d, 1, p)); holding = True; entry_px = p
                hold_hi, hhd = p, 0
    return evs, dates, ca


def px_nago(dates, closes, d, n):
    i = int(np.searchsorted(dates, d, side="right")) - 1
    if i - n < 0: return None, None
    return closes[i], closes[i - n]


def sim(sample, mode):
    info = {}
    for c in sample:
        df = fetch_daily_qfq_single(c, "2021-01-01", "2026-12-31")
        if df is None or len(df) <= 500: continue
        evs, dates, closes = gen(df)
        if not evs: continue
        def at(dd, da=dates, cc=closes):
            i = int(np.searchsorted(da, dd, side="right")) - 1
            return float(cc[max(i, 0)])
        info[c] = dict(evs=evs, at=at, dates=dates, closes=closes, ptr=0,
                       held=False, skip_sell=False)
    # 事件队: 按日期推进
    days = sorted({e[0] for d in info.values() for e in d["evs"]})
    cash = 1.0
    pos = {}            # code -> dict(shares, cost, peak, hhd)
    buys_done = sells_done = swaps = 0
    peaks, maxdd = [], 1.0
    for day in days:
        # 先按规则卖(独立链 sell event)
        for c, d in list(info.items()):
            evs = d["evs"]; ptr = d["ptr"]
            if ptr < len(evs) and evs[ptr][0] == day and not evs[ptr][1] and c in pos:
                sh = pos[c]["shares"]; cash += sh * evs[ptr][2]
                del pos[c]; d["ptr"] += 1; sells_done += 1
                if d["skip_sell"]: d["skip_sell"] = False
            elif ptr < len(evs) and evs[ptr][0] == day and not evs[ptr][1] and c not in pos:
                d["ptr"] += 1   # 无持仓时的卖事件(曾汰换)跳过
        # 买点候选(该日有 buy 事件的 idle 票)
        cands = []
        for c, d in info.items():
            ptr = d["ptr"]
            if ptr < len(d["evs"]) and d["evs"][ptr][0] == day and d["evs"][ptr][1] and not d["held"]:
                cands.append((c, d["evs"][ptr][2]))
        # mode=swap: 满员时汰弱换强
        if mode == "swap" and pos and len(pos) >= K and cands:
            eq = cash + sum(p["shares"] * info[c]["at"](day) for c, p in pos.items())
            # 最弱持仓(近5日跌幅最大)
            weak = None
            for c, p in pos.items():
                c5, c0 = px_nago(info[c]["dates"], info[c]["closes"], day, RET5_WIN)
                if c5 is None: continue
                ret = c5 / c0 - 1
                if weak is None or ret < weak[1]: weak = (c, ret)
            if weak:
                wc, wret = weak
                # 最强候选
                best = max(cands, key=lambda x: x[1] and 0 or 0)
                # 用候选近5日涨幅
                bcand = None
                for cc, _p in cands:
                    c5, c0 = px_nago(info[cc]["dates"], info[cc]["closes"], day, RET5_WIN)
                    if c5 is None: continue
                    r = c5 / c0 - 1
                    if bcand is None or r > bcand[1]: bcand = (cc, r)
                if bcand and bcand[1] - wret >= SWAP_EDGE and wret < 0:
                    wsh = pos[wc]["shares"]; cash += wsh * info[wc]["at"](day)
                    del pos[wc]; info[wc]["held"] = False; info[wc]["skip_sell"] = True
                    swaps += 1
                    cands = [(cc, px) for cc, px in cands if cc != bcand[0]]
        # 开新仓: 有空席且现金够
        eq_now = cash + sum(p["shares"] * info[c]["at"](day) for c, p in pos.items())
        for cc, px in sorted(cands, key=lambda x: x[1]):
            if len(pos) >= K: break
            alloc = min(cash, eq_now / K)
            if alloc <= 0: break
            sh = alloc / px
            cash -= alloc
            pos[cc] = dict(shares=sh, cost=px, peak=px, hhd=0)
            info[cc]["held"] = True
            info[cc]["ptr"] += 1
            buys_done += 1
        # 更新持仓 peak/hhd & 净值
        for c, p in pos.items():
            px = info[c]["at"](day)
            if px > p["peak"]: p["peak"], p["hhd"] = px, 0
            else: p["hhd"] += 1
        eq = cash + sum(p["shares"] * info[c]["at"](day) for c, p in pos.items())
        peaks.append(eq); mx = max(peaks)
        if mx > 0: maxdd = min(maxdd, eq / mx)
    eq = cash + sum(p["shares"] * info[c]["at"](END) for c, p in pos.items())
    return dict(final=eq, buys=buys_done, sells=sells_done, swaps=swaps, maxdd=maxdd)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "hold"
    mv = json.load(open(str(Path(__file__).parent.parent / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    step = max(1, len(big) // 200)
    sample = big[::step][:200]
    t0 = time.time()
    r = sim(sample, mode)
    print(f"[{mode}] K={K} 200只 2024-2026 | 期末{r['final']:.3f}({(r['final']-1)*100:+.0f}%) "
          f"回撤{(1-r['maxdd'])*100:.0f}% 买{r['buys']} 卖{r['sells']} 换{r['swaps']} | {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
