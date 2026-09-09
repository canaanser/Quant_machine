# -*- coding: utf-8 -*-
"""gen_next_plan — 收盘后生成明日买计划 (2026-09-09 新增, 供 duty_engine 14:44 自动执行)
口径:
  买点      : 无门筹码 n=3 套牢≥60% 且 5%≤底部≤20% (live_signal_daily.scan 复用)
  排序      : 队列替补语义 — 有 PIT 财报(好)优先: ROE高在前; 无财报垫后按筹码分
              (只排序不设门, 回测铁证门伤收益; ROE 取 pubDate<=基准日 的最新季, 无前视)
  仓位      : 分片买入, 每片上限 per(默认12000), 100股整手; 总预算 cash*0.96 留费/滑点缓冲
  输出      : outputs/next_plan.csv  (code, buy, shares, px_est, name)  引擎执行段按现价放单
用法(Windows cmd):
  python -B scripts/gen_next_plan.py --date 20260909           只出候选清单(审查)
  python -B scripts/gen_next_plan.py --date 20260909 --cash 43253 --write  写 next_plan.csv
"""
import json, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "core" / "lib"))
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from core.lib.emq_arch import latest_date as latest_archive_date
import logging
logging.getLogger("core.data_loader.freestockdb").setLevel(logging.ERROR)  # 静默每码INFO日志(GBK控制台会炸)
import csv
from live_signal_daily import scan  # 复用: 与每日信号扫描同一套已校准口径

OUT = PROJECT_ROOT / "outputs"


def pit_roe(code, asof):
    """PIT 最新ROE: 该季 pubDate <= asof(20260909) 的最近已披露季; 无则 None
    注意: pubDate是YYYY-MM-DD、asof是YYYYMMDD, 必须先统一成整数再比(字符串比会放未来披露进来=前视)"""
    asof_int = int(asof)
    q = json.load(open(OUT / "funda_pit_cache.json", encoding="utf-8")).get(code)
    if not q:
        return None
    best = None
    for qk, v in q.items():
        pd = v.get("pubDate")
        if pd and int(str(pd).replace("-", "")) <= asof_int:
            if best is None or pd > best["pubDate"]:
                best = v
    return best["roe"] if best and best.get("roe") is not None else None


def chip_score(s):
    return (1 if s["trap"] >= 80 else 0) + max(0, (20 - s["bot"]) / 10)



def held_codes():
    try:
        from core.trade.ledger import _load
        return list(_load()["positions"].keys())
    except Exception:
        return []


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="扫描基准日YYYYMMDD(默认: 东财归档最新交易日)")
    ap.add_argument("--cash", type=float, default=43253.0)
    ap.add_argument("--per", type=float, default=12000.0)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--save-json", action="store_true",
                    help="把当日排序后候选缓存到 outputs/candidates_<date>.json 供 compose_daily_plan 用")
    a = ap.parse_args()
    asof = a.date.replace("-", "") if a.date else (latest_archive_date() or "20260909")
    mv = json.load(open(str(OUT / "chip_mv_cache.json"), encoding="utf-8"))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    held = held_codes()
    print(f"[{asof}] 大池 {len(big)} | 已持仓 {held} | 预算 {a.cash:.0f}", flush=True)
    sigs = []
    for ci, code in enumerate(big):
        if code in held:
            continue
        r = scan(code, asof)
        if r:
            r["roe"] = pit_roe(code, asof)
            r["score"] = chip_score(r)
            sigs.append(r)
        if (ci + 1) % 150 == 0:
            print(f"  {ci + 1}/{len(big)}", flush=True)
    # 队列替补排序: 好财报(有PIT ROE)优先, ROE高在前; 无财报按筹码分; 都不设门
    sigs.sort(key=lambda x: (0 if x["roe"] is None else 1, x["roe"] if x["roe"] is not None else 0.0,
                             x["score"]), reverse=True)
    if a.save_json:
        jp = OUT / f"candidates_{asof}.json"
        json.dump(sigs, open(jp, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"候选缓存已存 {jp.name} ({len(sigs)} 只)")
    print(f"\n触发买点 {len(sigs)} 只")
    if not sigs:
        print("无候选 -> 明日不补买(engine 执行段自动判定卖)")
        return
    # 分片: 每片上限 per, 100股整手; 逐步吃预算
    budget = a.cash * 0.96
    plan, rest = [], budget
    for s in sigs:
        px = s["px"]
        cap = min(a.per, rest)
        lots = int(cap // (px * 100))
        if lots < 1:
            if px * 100 <= rest:
                lots = 1
            else:
                continue
        shares = lots * 100
        cost = shares * px
        if cost > rest + 1e-6:
            continue
        plan.append(dict(code=s["code"], name=s["name"], px=px, shares=shares, cost=cost,
                         trap=s["trap"], bot=s["bot"], roe=s["roe"]))
        rest -= cost
        if len(plan) >= 8 or rest < 5000:
            break
    print(f"\n可用预算 {budget:.0f} -> 计划 {len(plan)} 笔, 用 {budget - rest:.0f}, 剩 {rest:.0f}\n")
    hdr = f"{'代码':<8}{'名称':<10}{'现价':>8}{'股数':>7}{'金额':>9}{'套牢':>7}{'底部':>6}{'ROE':>7}"
    print(hdr)
    for p in plan:
        roe = f"{p['roe']:.2f}" if p["roe"] is not None else "-"
        nm = (p["name"][:5] + "..") if len(p["name"]) > 5 else p["name"]
        print(f"{p['code']:<8}{nm:<10}{p['px']:>8.2f}{p['shares']:>7}{p['cost']:>9.0f}"
              f"{p['trap']:>6.1f}%{p['bot']:>5.1f}%{roe:>7}")
    if a.write:
        with open(OUT / "next_plan.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["code", "side", "shares", "price", "name"])
            for p in plan:
                w.writerow([p["code"], "buy", p["shares"], round(p["px"], 2), p["name"]])
        # 审查留痕
        with open(OUT / "next_plan_review.txt", "w", encoding="utf-8") as f:
            f.write(f"基准日 {asof} | 预算 {a.cash:.0f}(96%={budget:.0f}) | 候选 {len(sigs)} | 计划 {len(plan)}\n")
            for p in plan:
                f.write(f"{p['code']} {p['name']} px={p['px']} sh={p['shares']} cost={p['cost']:.0f} "
                        f"trap={p['trap']} bot={p['bot']} roe={p['roe']}\n")
        print(f"\n已写 {OUT / 'next_plan.csv'}  (duty_engine 明日 14:44 自动执行)")


if __name__ == "__main__":
    main()
