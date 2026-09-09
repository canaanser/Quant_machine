# -*- coding: utf-8 -*-
"""
量能验真工具（2026-09-06 老板方法论固化）
==========================================
老板两条核心观察：
1. 换手率=真实成交验真器：剔股本干扰，比绝对成交量可信；低/中/高阈值因股而异
   → 用该股自身近 半年~1年 换手率滚动分位定标（p<20% 低 / p20-80 中 / >p80 高）
2. 主力资金看"两侧量能"不看净额：净流入+两侧(main_in/main_out)放大=真交易；
   净流入大但两侧小=可能自拉自唱（假）
   → 判据：两侧绝对值都大(近N日高分位) 才算"火热真交易"

识别信号：
  A. 低换手 + 急速下跌(|日跌|≥2%)  → 主力自砸/散户未接 → 假动作，勿恐慌割
  B. 低换手 + 急速上涨(≥2%)        → 主力试盘/少量拉价 → 观察非追
  C. 净流入>0 且 换手/两侧量能同步放大 → 真启动（有资金接力）

数据源（本地 stockdb HTTP，127.0.0.1:7899）：
  日K: 日k:{code}:{year}*  → turnover（换手率）/volume/amount/close
  资金流: 资金流:{code}*   → main_net/main_in/main_out/jumbo/big/mid/small
"""
import json
import urllib.request
import urllib.parse
import bisect
from datetime import datetime

HOST = "127.0.0.1:7899"
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get(expr: str):
    url = f"http://{HOST}/?cmd=get&t={urllib.parse.quote(expr)}"
    with _opener.open(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _clean_code(code: str) -> str:
    return "".join(c for c in str(code) if c.isdigit())[:6].zfill(6)


def daily(code: str, start="2025-01-01", end="2026-09-03"):
    """日K原始数据（不复权即可：换手率/资金流无需复权）"""
    code = _clean_code(code)
    y0 = int(start[:4]); y1 = int(end[:4])
    out = {}
    for y in range(y0, y1 + 1):
        rows = http_get(f"日k:{code}:{y}*")
        for item in rows:
            d = item[1]
            ds = str(d["date"])
            if start.replace("-", "") <= ds <= end.replace("-", ""):
                out[ds] = d
    return out


def fund_flow(code: str, start="2025-01-01", end="2026-09-03"):
    """主力资金流历史"""
    code = _clean_code(code)
    rows = http_get(f"资金流:{code}*")
    out = {}
    for item in rows:
        d = item[1]
        ds = str(d.get("date"))
        if start.replace("-", "") <= ds <= end.replace("-", ""):
            out[ds] = d
    return out


def turnover_percentile_map(code, window_days=180, start="2025-01-01", end="2026-09-03"):
    """滚动换手率分位：每个交易日用"该日之前 window_days 天"的换手率算 p20/p80
    返回 {date_str: (turnover, band)} band: '低'/'中'/'高'（按该日往前窗口自身分布）"""
    import statistics
    code = _clean_code(code)
    k = daily(code, start, end)
    dates = sorted(k.keys())
    out = {}
    for i, ds in enumerate(dates):
        tv = float(k[ds].get("turnover") or 0)
        win = [float(k[d].get("turnover") or 0) for d in dates[max(0, i - window_days):i]]
        if len(win) < 20:  # 窗口不足不判
            out[ds] = (tv, None)
            continue
        win_s = sorted(win)
        p20 = win_s[int(len(win_s) * 0.20)]
        p80 = win_s[min(len(win_s) - 1, int(len(win_s) * 0.80))]
        band = "高" if tv >= p80 else ("低" if tv <= p20 else "中")
        out[ds] = (tv, band)
    return out


def scan_fake_moves(code, name="", days=120, chg_thr=2.0, end="2026-09-03"):
    """扫描最近 N 天的 低换手假动作(A砸/B拉) + 真启动(C)"""
    code = _clean_code(code)
    k = daily(code, "2025-01-01", end)
    dates = sorted(d for d in k if d >= (end.replace("-", "")[:4] + "0101"))[-days:]
    tvmap = turnover_percentile_map(code, window_days=180, end=end)
    ff = fund_flow(code, end=end)
    signals = []
    for i, ds in enumerate(dates):
        rec = k.get(ds)
        if not rec:
            continue
        prev = k.get(dates[i - 1]) if i > 0 else None
        if not prev:
            continue
        chg = (float(rec["close"]) / float(prev["close"]) - 1) * 100
        tv, band = tvmap.get(ds, (None, None))
        if band is None:
            continue
        # 主力两侧量能（近20日分位）
        main_in = float(ff.get(ds, {}).get("main_in") or 0)
        main_out = float(ff.get(ds, {}).get("main_out") or 0)
        main_net = float(ff.get(ds, {}).get("main_net") or 0)
        side_sum = abs(main_in) + abs(main_out)
        # 两侧量能是否"火热"：近20日 sum 分位
        recent_sums = [abs(float(ff.get(d, {}).get("main_in") or 0)) +
                       abs(float(ff.get(d, {}).get("main_out") or 0))
                       for d in dates[max(0, i - 20):i] if d in ff]
        hot = False
        if recent_sums and side_sum >= sorted(recent_sums)[-1]:  # 当日两侧 > 近20日最大
            hot = True

        # 信号
        if band == "低" and chg <= -chg_thr:
            signals.append(("A_低换手急跌(主力砸?)", ds, chg, tv, main_net))
        elif band == "低" and chg >= chg_thr:
            signals.append(("B_低换手急拉(试盘?)", ds, chg, tv, main_net))
        elif main_net > 0 and hot:
            signals.append(("C_净流入+量能放大(真启动?)", ds, chg, tv, main_net))
    return signals, tvmap


if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "000063"
    name = sys.argv[2] if len(sys.argv) > 2 else code
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    sigs, _ = scan_fake_moves(code, name, days=days)
    print(f"=== {code} {name} 近{days}天 量能信号 ===")
    if not sigs:
        print("  无显著信号")
    for tag, ds, chg, tv, net in sigs:
        print(f"  {ds} {tag} 涨跌{chg:+.1f}% 换手{tv:.2f}% 主力净{net/1e4:+.0f}万")
