# -*- coding: utf-8 -*-
r"""全A筹码信号扫描（老板跑全量用，2026-09-06）

用途：不做任何"调参收敛"，只做普适性扫描 —— 门槛只管"信号定义"，输出按分档矩阵给老板自己看结论。

信号定义（纯筹码分布两维，无换手/无距低点等外部条件）：
  某日收盘，筹码分布满足：
    ① 套牢盘占比 ≥ trap_floor（默认 0.60，可用 --trap-min 改）
    ② 底部筹码（现价±5%内筹码占比）≥ bot5_floor（默认 0.05）
  仓位：套牢越重买越多（沿用测试机，w=(trap-0.55)/0.40）——但扫描器只统计信号质量，
        仓位影响另由回测机跑。

每个信号 = 空仓状态下的一个买入日；买后进入持有，先触 +TP 止盈 / −SL 止损 / 60日末平仓。
一只票同一时刻只持有一笔，平仓后才找下一信号 → 信号数 = 全A自然出现的次数。

输出：
  1. stdout 汇总：总信号数、胜率、平均收益、年度分布、套牢×底部筹码分档矩阵
  2. outputs/chip_scan_{tag}.csv：每笔信号明细（code,date,px,trap,bot5,peakdist,ret）可复查

用法（老板 Windows cmd）：
  cd /d E:\stockgate\Quant_Alpha_System
  python -B scripts\chip_fullmarket_scan.py --start 2022-06-01 --end 2026-09-03
  （可选 --trap-min 0.60 --bot5-min 0.05 --take-profit 0.20 --stop-loss 0.10）
  （可选 --codes 000063,600498 只扫指定票；默认全A 0/3/6 前缀约5200只）
"""
import sys, os, json, bisect, time
from pathlib import Path
import urllib.request, urllib.parse

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data_loader.freestockdb import fetch_daily_qfq_single

HOST = "127.0.0.1:7899"
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get(expr: str, retry=4):
    url = f"http://{HOST}/?cmd=get&t={urllib.parse.quote(expr)}"
    for a in range(retry):
        try:
            with _opener.open(url, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if a == retry - 1:
                raise
            time.sleep(0.3 * (a + 1))


def all_codes():
    """A股全集: 0(深主板) 3(创业板) 6(沪市) — 不含北交所"""
    d = http_get("股票代码")
    out = []
    for g in ["0", "3", "6"]:
        out.extend(c for c in d[g] if len(c) == 6)
    return sorted(set(out))


def scan_one(code, y0, d0, d1, TP, SL, trap_floor, bot5_floor,
             skip_st=True, skip_delist=True):
    """统一取数(qfq) + 筹码两维信号；返回 [(date, px, trap, bot5, peakdist, ret)]
    skip_st:     信号触发日该股若是 ST/*ST → 不算信号（实盘不会买，跌停卖不出）
    skip_delist: 触发日处于退市整理(名含"退市")→ 不算信号"""
    try:
        df = fetch_daily_qfq_single(code, f"{y0}-01-01", "2026-12-31")
    except Exception:
        return []
    if df is None or len(df) < 300:
        return []
    cols = ["open", "high", "low", "close", "turnover"]
    has_st = "is_st" in df.columns and "name" in df.columns
    rows = []
    for i, d in enumerate(df.index):
        r = dict(
            date=d.strftime("%Y%m%d"), o=df["open"].iloc[i], h=df["high"].iloc[i],
            l=df["low"].iloc[i], c=df["close"].iloc[i], t=df["turnover"].iloc[i])
        if has_st:
            r["is_st"] = bool(df["is_st"].iloc[i])
            r["name"] = str(df["name"].iloc[i] or "")
        else:
            r["is_st"] = False; r["name"] = ""
        rows.append(r)
    n = len(rows)
    if n < 300:
        return []
    import numpy as np
    la = np.array([r["l"] for r in rows]); ha = np.array([r["h"] for r in rows])
    ca = np.array([r["c"] for r in rows]); tv = np.array([r["t"] for r in rows])
    is_st_arr = np.array([r["is_st"] for r in rows])
    name_arr = np.array([r["name"] for r in rows])
    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    top = hi_max * 1.02 + w
    nb = int(top / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    dates = [r["date"] for r in rows]
    res = []
    state = 0  # 0空仓 1持仓
    entry_px = 0.0
    entry_meta = None
    for i in range(n):
        d = dates[i]
        # 筹码逐日维护（全部历史都滚，但窗口外不触发）
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
        p = ca[i]
        if d < d0 or d > d1:
            # 窗口外仍推进状态机（持仓的按止盈止损平）
            if state == 1:
                if p >= entry_px * (1 + TP) or p <= entry_px * (1 - SL):
                    state = 0
            continue
        if state == 1:
            if p >= entry_px * (1 + TP) or p <= entry_px * (1 - SL):
                ret = (p / entry_px - 1) * 100
                res.append(tuple(entry_meta) + (round(ret, 1),))
                state = 0
            continue
        # 空仓：算筹码两维
        if skip_st and is_st_arr[i]:
            continue
        nm = name_arr[i]
        if skip_delist and (nm.endswith("退") or "退市" in nm):
            continue
        c = chip / s
        trap = c[bins > p].sum() * 100
        bot5 = c[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
        if trap >= trap_floor * 100 and bot5 >= bot5_floor * 100:
            peak = float(bins[int(c.argmax())])
            state = 1
            entry_px = p
            entry_meta = [code, d, round(p, 2), round(trap, 1), round(bot5, 1),
                          round((p / peak - 1) * 100, 1)]
    # 持仓跨期末：按最后价结算
    if state == 1 and n > 0:
        ret = (ca[-1] / entry_px - 1) * 100
        res.append(tuple(entry_meta) + (round(ret, 1),))
    return res


def main():
    import argparse
    import numpy as np
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-06-01")
    ap.add_argument("--end", default="2026-09-03")
    ap.add_argument("--trap-min", type=float, default=0.60)
    ap.add_argument("--bot5-min", type=float, default=0.05)
    ap.add_argument("--take-profit", type=float, default=0.20)
    ap.add_argument("--stop-loss", type=float, default=0.10)
    ap.add_argument("--codes", default=None, help="逗号分隔指定票(自测用)，默认全A")
    ap.add_argument("--max-codes", type=int, default=0, help="只扫前N只(自测用)")
    args = ap.parse_args()

    d0 = args.start.replace("-", "")
    d1 = args.end.replace("-", "")
    y0 = max(2018, int(args.start[:4]) - 3)  # 数据起点：提前3年保证400日lookback
    TP, SL = args.take_profit, args.stop_loss
    trap_floor = args.trap_min
    bot5_floor = args.bot5_min

    if args.codes:
        codes = args.codes.split(",")
    else:
        codes = all_codes()
    if args.max_codes:
        codes = codes[:args.max_codes]

    print(f"全A筹码扫描 | 套牢≥{trap_floor:.0%} 底部筹码≥{bot5_floor:.0%} "
          f"止盈+{TP:.0%} 止损-{SL:.0%} | {args.start}~{args.end} | {len(codes)}只", flush=True)
    print("=" * 70, flush=True)

    t0 = time.time()
    all_sig = []
    done = 0
    for code in codes:
        sig = scan_one(code, y0, d0, d1, TP, SL, trap_floor, bot5_floor)
        all_sig.extend(sig)
        done += 1
        if done % 200 == 0:
            el = time.time() - t0
            rate = done / el
            left = (len(codes) - done) / rate if rate > 0 else 0
            print(f"  进度 {done}/{len(codes)} 信号{len(all_sig)} "
                  f"耗时{el:.0f}s 预计剩{left:.0f}s", flush=True)
    el = time.time() - t0
    print(f"扫描完成 {len(codes)}只 耗时{el:.0f}s 总信号 {len(all_sig)}", flush=True)

    if not all_sig:
        print("无信号")
        return

    # 落盘明细
    tag = f"t{int(trap_floor*100)}b{int(bot5_floor*100)}"
    outdir = Path(__file__).parent.parent / "outputs"
    outdir.mkdir(exist_ok=True)
    csvp = outdir / f"chip_scan_{tag}.csv"
    import csv as _csv
    with open(csvp, "w", newline="", encoding="utf-8-sig") as f:
        wr = _csv.writer(f)
        wr.writerow(["code", "date", "px", "trap", "bot5", "peakdist", "ret"])
        for s in all_sig:
            wr.writerow(s)
    print(f"明细已存 {csvp}")

    # 汇总
    rets = np.array([s[6] for s in all_sig])
    traps = np.array([s[3] for s in all_sig])
    bots = np.array([s[4] for s in all_sig])
    years = np.array([s[1][:4] for s in all_sig])
    print(f"\n总信号 {len(all_sig)} | 胜率{(rets > 0).mean()*100:.1f}% "
          f"平均{rets.mean():+.1f}% 中位{np.median(rets):+.1f}% | "
          f"年度: " + " ".join(f"{y}:{(years==y).sum()}" for y in sorted(set(years))))
    print(f"亏损占比{(rets<0).mean()*100:.1f}% | 触及止盈{(rets>=TP*100).mean()*100:.1f}% "
          f"触及止损{(rets<=-SL*100).mean()*100:.1f}%")

    # 分档矩阵（老板自己看普适结论，不做收敛）
    print("\n=== 套牢 × 底部筹码 分档：信号数(胜率%/平均收益%) ===")
    t_edges = [0.60, 0.70, 0.80, 0.90, 1.01]
    b_edges = [0.0, 0.10, 0.20, 0.30, 1.01]
    hdr = "套牢\\底部 "
    for bb in range(len(b_edges) - 1):
        hdr += f"| {b_edges[bb]*100:.0f}-{b_edges[bb+1]*100:.0f}% "
    print(hdr)
    for tt in range(len(t_edges) - 1):
        row = f"{t_edges[tt]*100:.0f}-{t_edges[tt+1]*100:.0f}% "
        for bb in range(len(b_edges) - 1):
            sel = [s for s in all_sig if t_edges[tt] <= s[3]/100 < t_edges[tt+1]
                   and b_edges[bb] <= s[4]/100 < b_edges[bb+1]]
            if len(sel) >= 5:
                r = np.array([s[6] for s in sel])
                row += f"| {len(sel)}笔 {(r>0).mean()*100:.0f}% {r.mean():+.0f}% "
            else:
                row += f"| {len(sel)}笔  --   "
        print(row)

    print("\n=== 底部筹码分档 ===")
    for bb in range(len(b_edges) - 1):
        sel = [s for s in all_sig if b_edges[bb] <= s[4]/100 < b_edges[bb+1]]
        if not sel: continue
        r = np.array([s[6] for s in sel])
        print(f"底部筹码{b_edges[bb]*100:.0f}-{b_edges[bb+1]*100:.0f}%: {len(sel)}笔 "
              f"胜率{(r>0).mean()*100:.0f}% 平均{r.mean():+.1f}%")
    print("\n=== 套牢分档 ===")
    for tt in range(len(t_edges) - 1):
        sel = [s for s in all_sig if t_edges[tt] <= s[3]/100 < t_edges[tt+1]]
        if not sel: continue
        r = np.array([s[6] for s in sel])
        print(f"套牢{t_edges[tt]*100:.0f}-{t_edges[tt+1]*100:.0f}%: {len(sel)}笔 "
              f"胜率{(r>0).mean()*100:.0f}% 平均{r.mean():+.1f}%")


if __name__ == "__main__":
    main()
