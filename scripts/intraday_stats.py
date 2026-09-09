# -*- coding: utf-8 -*-
"""intraday_stats — 83只池 日内波动/做T机会统计 (2026-09-10 学习第1批)
对每(股,日): 振幅、日内回落≥0.3%后反弹的低吸机会、冲高≥0.8%后回落的高抛机会。
目的: 挑出适合日内做T的票池/时段特征; A股T+1 -> 做T=底仓先卖后买, 本统计只描述波动机会(不下单假设)。
输入: outputs/min_samples/<code>.csv; 输出: outputs/intraday_stats.txt
"""
import csv
from pathlib import Path
ROOT = Path(__file__).parent.parent
SRC = ROOT / "outputs" / "min_samples"


def load(code):
    rows = []
    with open(SRC / f"{code}.csv", encoding="utf-8") as f:
        for ln in csv.DictReader(f):
            rows.append({"d": int(ln["date"]) // 1000000, "o": float(ln["open"]),
                         "h": float(ln["high"]), "l": float(ln["low"]),
                         "c": float(ln["close"])})
    return rows


def day_ops(rows):
    days = {}
    for r in rows:
        days.setdefault(r["d"], []).append(r)
    return days


def main():
    out = []
    all_days = 0
    rows_by = {}
    for fp in sorted(SRC.glob("*.csv")):
        code = fp.stem
        rows_by[code] = day_ops(load(code))
    # 每(股,日)统计
    per_code = {}
    for code, days in rows_by.items():
        n = 0
        amps = []
        dip_recover = 0   # 创新低后 3根内反弹>=+0.3% (低吸机会)
        pop_back = 0      # 冲高>=+0.8%后回落>=0.3% (高抛T机会)
        for d, ms in sorted(days.items()):
            n += 1
            hi = max(m["h"] for m in ms)
            lo = min(m["l"] for m in ms)
            o = ms[0]["o"]
            if o <= 0:
                continue
            amps.append((hi - lo) / o * 100)
            # 回落反弹
            for i in range(1, len(ms)):
                if ms[i]["l"] <= lo * 1.0005 and ms[i]["c"] < o:
                    if i + 3 < len(ms):
                        fut = min(ms[j]["l"] for j in range(i, min(i + 4, len(ms))))
                        if fut >= ms[i]["c"] * 1.003:
                            dip_recover += 1
                    break
            # 冲高回落(高抛)
            for i in range(1, len(ms)):
                if ms[i]["h"] >= o * 1.008:
                    after = min(ms[j]["h"] for j in range(i + 1, len(ms))) if i + 1 < len(ms) else ms[i]["h"]
                    if after <= ms[i]["h"] * 0.997:
                        pop_back += 1
                    break
        if n == 0:
            continue
        all_days += n
        per_code[code] = (n, sum(amps) / n, dip_recover / n, pop_back / n)
    out.append(f"样本: 83只 x 每只{n}日 (当日无分钟按n记) | 总计日 {all_days}")
    hdr = f"{'code':<8}{'日数':>4}{'日均振幅%':>9}{'低吸机/日':>9}{'高抛机/日':>9}"
    out.append(hdr)
    for code, (n, am, di, po) in sorted(per_code.items(), key=lambda x: -x[1][1]):
        if am >= 1.2 and n >= 8:   # 振幅>=1.2%才有做T空间
            out.append(f"{code:<8}{n:>4}{am:>9.2f}{di:>9.2f}{po:>9.2f}")
    text = "\n".join(out)
    print(text)
    (ROOT / "outputs" / "intraday_stats.txt").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
