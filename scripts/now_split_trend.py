# -*- coding: utf-8 -*-
"""115只命中票 区分: 东方电缆型(阴跌不止,别碰) vs 真恐慌底(可能企稳)
对每只算: 近5/20日收益(还在跌?), 距250日高/低, MA5vsMA20, 是否创20日新低
东方电缆 603606 作参照(它符合筹码买点但趋势坏阴跌不止)
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import numpy as np
from core.data_loader.freestockdb import fetch_daily_qfq_single

codes = [c.strip() for c in open(PROJECT_ROOT / "outputs/bigcap_now_codes.txt").read().split() if c.strip()]


def trend(code):
    df = fetch_daily_qfq_single(code, "2024-01-01", "2026-09-05")
    if df is None or len(df) < 260:
        return None
    c = df["close"].values
    p = c[-1]
    ma5 = c[-5:].mean()
    ma20 = c[-20:].mean()
    ma60 = c[-60:].mean()
    ret5 = (p / c[-6] - 1) * 100 if len(c) > 6 else 0
    ret20 = (p / c[-21] - 1) * 100 if len(c) > 21 else 0
    hi250 = c[-250:].max()
    lo250 = c[-250:].min()
    newlo20 = p <= c[-21:].min() * 1.01  # 近20日低点附近=还在阴跌
    return dict(ret5=ret5, ret20=ret20, dd_hi=(p / hi250 - 1) * 100,
                up_lo=(p / lo250 - 1) * 100, above_ma20=p > ma20,
                ma5_gt_20=ma5 > ma20, ma20_gt_60=ma20 > ma60, newlo20=bool(newlo20))


# 东方电缆参照
zd = trend("603606")
print(f"东方电缆(参照,阴跌不止型): ret5={zd['ret5']:+.1f}% ret20={zd['ret20']:+.1f}% "
      f"距250高{zd['dd_hi']:+.0f}% MA5>MA20={zd['ma5_gt_20']} 创20日低={zd['newlo20']}\n")

falling, mixed, ok = [], [], []
for c in codes:
    t = trend(c)
    if t is None:
        continue
    if t["newlo20"] and not t["ma5_gt_20"] and t["ret5"] < 0:
        falling.append((c, t))      # 阴跌不止型: 创20日低+死叉+近5日还在跌
    elif t["ma5_gt_20"] and t["ret5"] > 0:
        ok.append((c, t))           # 开始企稳/反弹: 金叉+近5日涨
    else:
        mixed.append((c, t))
print(f"115只分型: 东方电缆型(阴跌不止) {len(falling)} | 企稳反弹 {len(ok)} | 中间态 {len(mixed)}\n")
print("=== ⚠️ 东方电缆型(还在阴跌,别碰,像东方电缆) ===")
for c, t in falling:
    print(f"  {c} ret5={t['ret5']:+.1f}% ret20={t['ret20']:+.1f}% 距250高{t['dd_hi']:+.0f}% 20日低=Y")
print("\n=== ✅ 企稳反弹型(跌到位开始金叉,相对安全) ===")
for c, t in ok:
    print(f"  {c} ret5={t['ret5']:+.1f}% ret20={t['ret20']:+.1f}% 距250高{t['dd_hi']:+.0f}%")
open(PROJECT_ROOT / "outputs/bigcap_now_split.txt", "w", encoding="utf-8").write(
    f"falling {len(falling)}\n" + "\n".join(x[0] for x in falling) + "\n\nok\n" + "\n".join(x[0] for x in ok))
