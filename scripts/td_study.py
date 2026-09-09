# -*- coding: utf-8 -*-
"""td_study — 账户2 做T 规则离线研究 (2026-09-10 凌晨)
合规: A股T+1 -> 用昨日底仓做"先卖后买"(T卖: 价冲高卖半仓底仓; 买回: 回落接回)。
锚: 分时VWAP(累计额/累计量)。规则a=价>VWAP*(1+x)卖半仓; 之后价<=(VWAP*(1+y)或卖价*(1-z))买回。
成本: 卖 佣金0.025%+印花0.05%, 买 佣金0.025%; 滑点不计(取成交分钟收盘近似)。
输入 outputs/min_samples/*.csv; 输出 outputs/td_study.txt
用法: python -B scripts/td_study.py
"""
import csv
from pathlib import Path
ROOT = Path(__file__).parent.parent
SRC = ROOT / "outputs" / "min_samples"
FEE_S = 0.00025 + 0.0005   # 卖 佣金+印花
FEE_B = 0.00025            # 买 佣金
BASE = 10000.0             # 每(股,日)底仓市值


def load(code):
    rows = []
    with open(SRC / f"{code}.csv", encoding="utf-8") as f:
        for ln in csv.DictReader(f):
            rows.append({"d": int(ln["date"]) // 1000000, "o": float(ln["open"]),
                         "h": float(ln["high"]), "l": float(ln["low"]),
                         "c": float(ln["close"]), "v": float(ln["volume"] or 0),
                         "a": float(ln["amount"] or 0)})
    days = {}
    for r in rows:
        days.setdefault(r["d"], []).append(r)
    return days


def sim(ms, x, y):
    """规则a: 以 VWAP 为锚的底仓T。返回 (完成T次数, 净收益元, 半途未买回次数, 已卖总股)"""
    if len(ms) < 60:
        return 0, 0.0, 0, 0
    cum_a = 0.0
    cum_v = 0.0
    i_start = 10           # 09:40 前后开始做T(开盘噪音避开)
    base_px = ms[i_start]["c"]
    if base_px <= 0:
        return 0, 0.0, 0, 0
    hold = BASE / base_px            # 底仓股数(10手内, 按钱)
    sell_sh = hold / 2.0             # T卖半仓
    sold = None                      # (价, 股) 待买回
    done = 0
    miss = 0
    net = 0.0
    for i in range(len(ms)):
        m = ms[i]
        cum_a += m["a"]
        cum_v += m["v"]
        if i < i_start:
            continue
        vwap = cum_a / cum_v if cum_v > 0 else m["c"]
        if vwap <= 0:
            vwap = m["c"]
        if sold is None:
            if m["h"] >= vwap * (1 + x):
                sold = (m["c"], sell_sh)
        else:
            # 买回: 价触及 均价下方 y 或低于卖价*(1-0.6x)
            back_px = min(vwap * (1 - y), sold[0] * (1 - 0.6 * x))
            if m["l"] <= back_px:
                net += (sold[0] - m["c"]) * sold[1]
                net -= sold[0] * sold[1] * FEE_S + m["c"] * sold[1] * FEE_B
                done += 1
                sold = None
    if sold is not None:
        miss += 1                       # 当日没接回=实质减仓半仓
    return done, net, miss, sell_sh


def main():
    files = sorted(SRC.glob("*.csv"))
    grid = [(0.004, 0.002), (0.006, 0.003), (0.008, 0.004)]
    print("文件代码数:", len(files))
    # 按(股,日)汇总
    per_cfg = {}
    detail = {}
    for fp in files:
        code = fp.stem
        days = load(code)
        for d, ms in days.items():
            for x, y in grid:
                k = (x, y)
                d_, net, miss, sh = sim(ms, x, y)
                if d_ or miss:
                    per_cfg.setdefault(k, [0, 0.0, 0])
                    per_cfg[k][0] += d_
                    per_cfg[k][1] += net
                    per_cfg[k][2] += miss
                    if d_:
                        detail.setdefault(k, {}).setdefault(code, [0, 0.0]) 
                        detail[k][code][0] += d_
                        detail[k][code][1] += net
    out = []
    out.append(f"底仓T规则a(半仓 VWAP锚): 83只 x 10日 | 每(股,日)底仓{BASE:.0f}元")
    for (x, y), (n, net, miss) in sorted(per_cfg.items(), key=lambda t: -t[1][1]):
        out.append(f"卖触发+{x*100:.1f}% 买回-{y*100:.1f}% | 完成T{n}次 净{net:+,.0f}元 "
                   f"均净/次{net/n if n else 0:+,.0f}元 半途未接回{miss}次")
    # 最优参数下各票表现(前15)
    if per_cfg:
        best = max(per_cfg.items(), key=lambda t: t[1][1])[0]
        x, y = best
        out.append(f"\n最佳参数 卖+{x*100:.1f}% 买回-{y*100:.1f}% 的分票净收益(前15):")
        codes = detail.get(best, {})
        for code, (n, net) in sorted(codes.items(), key=lambda t: -t[1][1])[:15]:
            out.append(f"  {code}: {n}次 净{net:+,.0f}元")
    text = "\n".join(out)
    print(text)
    (ROOT / "outputs" / "td_study.txt").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
