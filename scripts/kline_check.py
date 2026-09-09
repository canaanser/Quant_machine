# -*- coding: utf-8 -*-
"""40只命中票 K线形态分型(2026-09-06 老板: 真底部才要, 下跌中/拉升后都不要)
对每只近120日判断:
  - 是否近期大拉(近20日涨幅>15% 或 近5日>8%)→ '拉升后' ❌
  - 是否仍在阴跌创新低(近20日跌&现价≈20日低) → '下跌中' ❌(未企稳)
  - 否则 → 看是否低位企稳(距250高深跌>30% 且 近10日不创新低/横盘) → '真底部' ✅ / '底部待确认'
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import numpy as np
from core.data_loader.freestockdb import fetch_daily_qfq_single

# 从 n=3 命中名单取代码(bigcap_now.txt 已被run2覆盖为40只)
codes = []
started = False
for ln in open(PROJECT_ROOT / "outputs/bigcap_now.txt", encoding="utf-8").read().splitlines():
    parts = ln.split()
    if ln.startswith("✅"):
        started = True; continue
    if ln.startswith("⚠️"):
        break
    if started and parts and parts[0].isdigit() and len(parts) >= 7:
        codes.append(parts[0])


def classify(code):
    df = fetch_daily_qfq_single(code, "2025-01-01", "2026-09-05")
    if df is None or len(df) < 120:
        return None
    c = df["close"].values
    p = c[-1]
    ret5 = (p / c[-6] - 1) * 100
    ret20 = (p / c[-21] - 1) * 100 if len(c) > 21 else 0
    ret60 = (p / c[-61] - 1) * 100 if len(c) > 61 else 0
    lo20 = c[-20:].min()
    hi120 = c[-120:].max()
    # 近期最高点出现位置
    hi_idx = int(np.argmax(c[-120:]))
    days_since_hi = 119 - hi_idx
    # 近5日是否有大阳
    big5 = max((c[-j] / c[-j - 1] - 1) for j in range(1, 6)) * 100 if len(c) > 6 else 0
    state = None
    if ret5 > 8 or ret20 > 15:
        state = "拉升后❌"
    elif p <= lo20 * 1.03 and ret20 < -5:
        state = "下跌中❌"
    elif ret20 >= 0 and ret5 >= 0 and days_since_hi <= 30:
        state = "拉升后?❌"
    elif (p / hi120 - 1) < -0.25 and ret20 >= -5:
        # 深跌后近20日企稳(不创新低,小波动)
        state = "真底部✅" if ret5 >= -2 else "底部待确认⚠️"
    elif (p / hi120 - 1) < -0.15:
        state = "深跌中⚠️"
    else:
        state = "高位/不明❌"
    return dict(code=code, p=p, ret5=ret5, ret20=ret20, ret60=ret60,
                dd120=(p / hi120 - 1) * 100, dsh=days_since_hi, big5=big5, state=state)


def main():
    names = {}
    for ln in open(PROJECT_ROOT / "outputs/bigcap_now_run2.txt", encoding="utf-8").read().splitlines():
        parts = ln.split()
        if parts and parts[0].isdigit() and len(parts) >= 2:
            names[parts[0]] = " ".join(parts[1:-5])
    groups = {}
    for c in codes:
        r = classify(c)
        if r is None:
            continue
        groups.setdefault(r["state"], []).append(r)
    for g in ["真底部✅", "底部待确认⚠️", "深跌中⚠️", "下跌中❌", "拉升后❌", "拉升后?❌", "高位/不明❌"]:
        if g not in groups:
            continue
        print(f"\n== {g} ({len(groups[g])}只) ==")
        for r in sorted(groups[g], key=lambda x: x["ret20"]):
            print(f"  {r['code']} {names.get(r['code'],''):<9} 收{r['p']:.2f} "
                  f"5日{r['ret5']:+.1f}% 20日{r['ret20']:+.1f}% 距120高{r['dd120']:+.0f}% 距高{r['dsh']}日")


if __name__ == "__main__":
    main()
