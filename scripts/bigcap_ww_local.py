# -*- coding: utf-8 -*-
"""大票池 × 本地王文项分层（无财报版, 2026-09-06 老板）
用本地现成数据能给627只全打的王文项:
  ① 估值: 当日 pe_ttm / pb (日K带, T日实时)
  ③ 分红: 复权表 div>0 即分过红
不可用(要财报): ocf/毛利净利/yoy —— 跳过
做法: 对每只大票取 2026 最近日 pe/pb → 分位打分 → 高低两组看收益分布
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import numpy as np
import urllib.request, urllib.parse

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get(t):
    url = f"http://127.0.0.1:7899/?cmd=get&t={urllib.parse.quote(t)}"
    with _opener.open(url, timeout=20) as r:
        return json.loads(r.read().decode())


def last_pe_pb(code):
    for y in ("2026", "2025"):
        try:
            rows = http_get(f"日k:{code}:{y}*")
        except Exception:
            return None, None, None
        for it in reversed(rows):
            r = it[1]
            if r and r.get("pe_ttm") and r.get("pb"):
                return (float(r["pe_ttm"]), float(r["pb"]), r.get("date"))
    return None, None, None


def main():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rows = json.load(open(os.path.join(root, "outputs/bigcap_ladder.json")))
    print(f"大票627只, 拉 pe/pb...", flush=True)
    data = []
    for i, (code, nav, nt) in enumerate(rows):
        pe, pb, d = last_pe_pb(code)
        data.append({"code": code, "nav": nav, "pe": pe, "pb": pb, "d": d})
        if (i + 1) % 150 == 0:
            print(f"  {i+1}/627", flush=True)
    import pandas as pd
    df = pd.DataFrame(data)
    df["ret"] = (df["nav"] - 1) * 100
    ok_val = (df["pe"] > 0) & (df["pe"] < 30) & (df["pb"] < 5)
    print(f"\n=== 王文项①低估值(pe<30 & pb<5 & pe>0, 本地实时) ===")
    for nm, m in [("达标", ok_val), ("不达标", ~ok_val)]:
        sub = df[m]
        if len(sub) == 0:
            continue
        print(f"[{nm}] {len(sub)}只 期望{sub['ret'].mean():+.1f}% 中位{np.median(sub['ret']):+.1f}% "
              f"盈利{(sub['ret']>0).mean()*100:.0f}%")
    # 连续: 按pe分位
    dfq = df[df["pe"] > 0].copy()
    dfq["pe_q"] = dfq["pe"].rank(pct=True)
    print(f"\n=== 按PE分位四组 ===")
    for lo, hi in [(0, .25), (.25, .5), (.5, .75), (.75, 1.01)]:
        sub = dfq[(dfq["pe_q"] >= lo) & (dfq["pe_q"] < hi)]
        print(f"PE分位{lo:.0%}-{hi:.0%} (pe中位{np.median(sub['pe']):.0f}): "
              f"{len(sub)}只 期望{sub['ret'].mean():+.1f}% 中位{np.median(sub['ret']):+.1f}% "
              f"盈利{(sub['ret']>0).mean()*100:.0f}%")
    df.to_json(os.path.join(root, "outputs/bigcap_ww_local.json"),
               orient="records", force_ascii=False)


if __name__ == "__main__":
    main()
