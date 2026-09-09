# -*- coding: utf-8 -*-
"""抄底池 v2: 队列补位 + 周汰弱 + 账户水位闸 (2026-09-09, 老板全权)
池: K=8席; 每席=净值1/8; 买点=无门筹码(同昨日验证口径); 卖出=防崩/峰顶/滞涨(sellrules).
队列: 满员时的买点进等待队列(不丢), 空席按先到先补.
周汰弱(可选): 每5交易日检: 持仓中 近5日仍跌 且 水下未回本 的最弱者清出(保留≥2席), 等信号补.
水位闸(可选, 老板核心): 只看账户水位=1-净值/峰值. 按回撤档收放:
   档位: dd<6% 满额; <10% 0.75; <16% 0.5; ≥16% 0.25且停新开; 恢复线=档位一半(滞回,防刚回本就加满)
  (闸只控"能开多少新仓/开不开", 不替策略选票; 卖出照规则)
用法: python -B scripts/pool_test2.py <q|qc|qg|qcg> > outputs/pool2_<m>.txt
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
CULL_WIN, CULL_FLOOR = 5, 2


def gen(df):
    ca, la, ha, tv = df["close"].values, df["low"].values, df["high"].values, df["turnover"].values
    dates = np.array([int(str(d.date()).replace("-", "")) for d in df.index])
    N = len(df)
    hi_max = float(ha.max()); w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1; bins = np.arange(nb) * w
    chip = np.zeros(nb)
    evs = []
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


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "q"
    do_cull = mode in ("qc", "qcg")
    do_gov = mode in ("qg", "qcg")
    do_deep = mode == "qd"      # 深水主动减仓(滞回)实验
    do_ten = mode == "qh"       # 持仓时间维: 满10交易日仍不涨 -> 卖一半
    mv = json.load(open(str(Path(__file__).parent.parent / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    step = max(1, len(big) // 200)
    sample = big[::step][:200]
    t0 = time.time()
    info = {}
    for c in sample:
        df = fetch_daily_qfq_single(c, "2021-01-01", "2026-12-31")
        if df is None or len(df) <= 500: continue
        evs, dates, closes = gen(df)
        if not evs: continue
        def at(dd, da=dates, cc=closes):
            i = int(np.searchsorted(da, dd, side="right")) - 1
            return float(cc[max(i, 0)])
        def nago(dd, n, da=dates, cc=closes):
            i = int(np.searchsorted(da, dd, side="right")) - 1
            if i - n < 0: return None
            return float(cc[i - n])
        info[c] = dict(evs=evs, at=at, nago=nago, ptr=0)
    days = sorted({e[0] for d in info.values() for e in d["evs"]})
    cash = 1.0
    pos = {}
    queue = []            # (date_first, code)
    queued = set()
    peak_eq, gov = 1.0, 1.0
    max_dd = 0.0; days_dd10 = 0; days_dd16 = 0
    buys = sells = culls = 0
    blocked = 0
    eq_hist = []
    last_review = -100
    deep_on = False
    ymarks = {}
    n_days = 0

    def gov_cap(dd):
        if dd < 0.06: return 1.0
        if dd < 0.10: return 0.75
        if dd < 0.16: return 0.5
        return 0.25

    for day in days:
        # 1) 规则卖(链 sell event)
        for c, d in info.items():
            evs = d["evs"]; ptr = d["ptr"]
            if ptr < len(evs) and evs[ptr][0] == day and not evs[ptr][1]:
                if c in pos:
                    cash += pos[c]["shares"] * evs[ptr][2]
                    del pos[c]; sells += 1
                    if c in queued: queued.discard(c)
                d["ptr"] += 1
        eq = cash + sum(p["shares"] * info[c]["at"](day) for c, p in pos.items())
        peak_eq = max(peak_eq, eq)
        dd_now = 1 - eq/peak_eq
        max_dd = max(max_dd, dd_now)
        if dd_now >= 0.10: days_dd10 += 1
        if dd_now >= 0.16: days_dd16 += 1
        dd = 1 - eq / peak_eq if peak_eq else 0
        cap = gov_cap(dd) if do_gov else 1.0
        # 2) 周汰弱
        n_days += 1
        if do_cull and n_days - last_review >= 5:
            last_review = n_days
            while len(pos) > CULL_FLOOR:
                wk = None
                for c, p in pos.items():
                    if p["pnl0"] is None: continue
                    n5 = info[c]["nago"](day, CULL_WIN)
                    if n5 is None: continue
                    r5 = info[c]["at"](day) / n5 - 1
                    if r5 < 0 and p["pnl0"] <= 0:
                        if wk is None or r5 < wk[1]: wk = (c, r5)
                if wk is None: break
                cash += pos[wk[0]]["shares"] * info[wk[0]]["at"](day)
                del pos[wk[0]]; culls += 1
        # 2.5) 深水温和缩仓(滞回, v2): 仅 dd>=16% 触发, 每仓缩到85%(按比例, 不整卖弱票), 回<8%恢复
        if do_deep:
            if dd_now >= 0.25:
                deep_on = True
            elif dd_now < 0.12:
                deep_on = False
            if deep_on and pos:
                for cc in list(pos):
                    pp = pos[cc]
                    if pp["shares"] <= 0:
                        continue
                    px = info[cc]["at"](day)
                    keep = pp["shares"] * 0.90
                    cash += (pp["shares"] - keep) * px
                    pp["shares"] = keep
                    culls += 1
        # 2.6) 持仓时间维: 满10交易日且仍未回本(pnl<=0) -> 卖一半(防死等僵尸)
        if do_ten:
            for cc in list(pos):
                pp = pos[cc]
                hold_days = n_days if False else 0
                if pp.get("date0") and day - pp["date0"] >= 10 and pp.get("pnl0", 0) <= 0:
                    if pp["shares"] > 100:
                        sell_sh = pp["shares"] * 0.5
                        cash += sell_sh * info[cc]["at"](day)
                        pp["shares"] -= sell_sh
                        pp["date0"] = day       # 重计窗口(避免天天切)
                        culls += 1
        # 3) 空席补位(先队列, 后当日新买点)
        cands = []
        for c, d in info.items():
            ptr = d["ptr"]
            if ptr < len(d["evs"]) and d["evs"][ptr][0] == day and d["evs"][ptr][1] and c not in pos:
                cands.append(c)
        for c in cands:
            if c not in queued:
                queue.append((day, c)); queued.add(c)
        # 有效席数 = K*cap
        slots = int(K * cap)
        while pos.__len__() < slots and queue:
            c = queue[0][1]
            if c in pos:
                queue.pop(0); queued.discard(c); continue
            px = info[c]["at"](day)
            alloc = min(cash, eq / K)
            if alloc <= 0: break
            cash -= alloc
            pos[c] = dict(shares=alloc / px, cost=px, peak=px, hhd=0, pnl0=0.0, pxnow=px, date0=day)
            info[c]["ptr"] += 1
            buys += 1
            queue.pop(0); queued.discard(c)
        # 收盘后更新持仓状态 & 记录
        for c, p in pos.items():
            px = info[c]["at"](day)
            p["pxnow"] = px
            p["pnl0"] = px / p["cost"] - 1
            if px > p["peak"]: p["peak"], p["hhd"] = px, 0
            else: p["hhd"] += 1
        eq = cash + sum(p["shares"] * info[c]["at"](day) for c, p in pos.items())
        peak_eq = max(peak_eq, eq)
        dd_now = 1 - eq/peak_eq
        max_dd = max(max_dd, dd_now)
        if dd_now >= 0.10: days_dd10 += 1
        if dd_now >= 0.16: days_dd16 += 1
        for y in (20241231, 20251231):
            if day >= y and y not in ymarks:
                ymarks[y] = eq
        # 水位闸: 停新开则阻塞计数(用下一天生效; 简化: 记录当前挡)
        if do_gov and cap < 1.0:
            blocked += 1
    eq = cash + sum(p["shares"] * info[c]["at"](END) for c, p in pos.items())
    ymarks[END] = eq
    dd_final = max(0.0, 1 - min(eq / peak_eq if peak_eq else 1, 1))
    print(f"[{mode}] K={K} cull={do_cull} gov={do_gov} | 期末{eq:.3f}({(eq-1)*100:+.0f}%) "
          f"买{buys} 卖{sells} 汰{culls} 压闸{blocked}天 | 峰值回撤见下")
    print(f"  年净值: 2024={ymarks.get(20241231,0):.2f} 2025={ymarks.get(20251231,0):.2f} 末={eq:.2f}")
    # 日净值峰值回撤粗略(每事件日样本)
    print(f"  峰值回撤{max_dd*100:.1f}% | 水位≥10%{days_dd10}天 ≥16%{days_dd16}天 | 用时{time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
