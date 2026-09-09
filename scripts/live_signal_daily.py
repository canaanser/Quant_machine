# -*- coding: utf-8 -*-
r"""实盘组合策略 v1.0 无门最终版 — 每日信号扫描(收盘后跑, 老板模拟盘用, 2026-09-07)
口径全部来自已验证成果:
  池        : 市值≥300亿 A股, 排除ST/退市
  买点      : 纯筹码n=3 套牢≥60% 且 5%≤底部≤20% (贴东财校准)
  无过滤门  : 回测铁证任何门(企稳/深度/位置/估值)都砍收益 → 只按筹码排序
  卖(纪律)  : 峰顶跟踪(浮盈≥30%后回落2%/滞涨15日) + 防崩-12%认错
  组合排序  : 套牢深优先(≥80) + 底部干净优先 → 输出前N只
用法(Windows cmd 权威):
  python -B scripts/live_signal_daily.py [--date 2026-09-07] [--top 10]
"""
import sys, json
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import numpy as np
from core.data_loader.freestockdb import fetch_daily_qfq_single

TRAP_MIN = 60.0
BOT_LO, BOT_HI = 5.0, 20.0


def scan(code, asof):
    """返回该票 asof 日的信号 dict 或 None"""
    df = fetch_daily_qfq_single(code, "2025-01-01", "2026-12-31")
    if df is None or len(df) < 250:
        return None
    dates = np.array([str(d.date()).replace("-", "") for d in df.index])
    hits = np.where(dates == asof)[0]
    if len(hits) == 0:
        return None
    i = int(hits[0])
    la = df["low"].values; ha = df["high"].values
    ca = df["close"].values; tv = df["turnover"].values
    # 筹码(n=3) 截至 i
    hi_max = float(ha[i-300:i].max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    for j in range(max(0, i - 400), i):
        t = tv[j]
        if t > 0 and ha[j] > 0:
            alpha = min(t / 100.0 * 3.0, 1.0)
            chip *= (1 - alpha)
            m = (bins >= la[j] - 1e-9) & (bins <= ha[j] + 1e-9)
            if m.any():
                chip[m] += alpha / m.sum()
    s = chip.sum()
    if s <= 0:
        return None
    c = chip / s
    p = ca[i]
    trap = c[bins > p].sum() * 100
    bot = c[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
    if not (trap >= TRAP_MIN and BOT_LO <= bot <= BOT_HI):
        return None
    # 参考指标(不设过滤门 - 回测证明门伤收益)
    ret5 = (p / ca[i-5] - 1) * 100 if i >= 5 else 0
    lo20 = ca[max(0, i-20):i+1].min()
    dd_lo20 = (p / lo20 - 1) * 100 if lo20 > 0 else 0
    hi120 = ca[max(0, i-120):i+1].max()
    dd_hi120 = (p / hi120 - 1) * 100 if hi120 > 0 else 0
    nm = str(df["name"].iloc[-1]) if "name" in df.columns else ""
    return dict(code=code, name=nm, date=asof, px=round(float(p), 2), trap=round(trap, 1),
                bot=round(bot, 1), ret5=round(ret5, 1), dd_lo20=round(dd_lo20, 1),
                dd_hi120=round(dd_hi120, 1))


def main():
    import argparse
    from core.data_loader.freestockdb import fetch_daily_qfq_single
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="扫描基准日(默认最新交易日)")
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    # 默认最新日
    asof = a.date
    if not asof:
        probe = fetch_daily_qfq_single("000063", "2026-09-01", "2026-12-31")
        asof = str(probe.index[-1].date()).replace("-", "") if probe is not None and len(probe) else "20260907"
    print(f"扫描基准日 {asof} | 池 {len(big)} 只(≥300亿) | 买点: 套牢≥60 底5-20 (无过滤门)", flush=True)
    sigs = []
    for ci, code in enumerate(big):
        r = scan(code, asof)
        if r:
            sigs.append(r)
        if (ci + 1) % 150 == 0:
            print(f"  {ci+1}/{len(big)}", flush=True)
    # 排序(不是过滤): 套牢深优先(>=80) + 底部洗得透优先(回测验证的纯筹码逻辑)
    for s in sigs:
        s["score"] = (1 if s["trap"] >= 80 else 0) + max(0, (20 - s["bot"]) / 10)
    sigs.sort(key=lambda x: -x["score"])
    print(f"\n触发买点 {len(sigs)} 只")
    print(f"\n{'代码':<8}{'名称':<10}{'收盘':>8}{'套牢':>7}{'底部':>7}{'5日':>7}{'距20低':>8}{'距120高':>9}")
    for s in sigs[:a.top]:
        nm = (s["name"][:5] + "..") if len(s["name"]) > 5 else s["name"]
        print(f"{s['code']:<8}{nm:<10}{s['px']:>8.2f}{s['trap']:>6.1f}%{s['bot']:>6.1f}%"
              f"{s['ret5']:>+6.1f}%{s['dd_lo20']:>+7.1f}%{s['dd_hi120']:>+8.1f}%")
    print(f"\n(前{a.top}只按套牢深度+筹码干净度排序。买入纪律见策略文档)")


if __name__ == "__main__":
    main()
