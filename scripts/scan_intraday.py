# -*- coding: utf-8 -*-
r"""盘中近似全量扫描 (2026-09-08 14:30, 距收盘<30分钟)
口径: 本地日线(至9/7) + 今日实时快照(腾讯 high/low/vol/amount) 拼"今日近似K线",
用同一筹码算法(n=3, 当日换手≈昨换手×(今量/昨量), 顶部减仓幅度由盘中折价近似)算套牢/底部。
⚠️ 近似: 今日未收盘, 量/换手未走完; 仅供盘中参考, 收盘后以正式扫描为准。
用法(Windows): E:\python\python.exe -B scripts\scan_intraday.py > outputs\scan_intraday_0908.txt
"""
import io, json, sys, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from core.data_loader.freestockdb import fetch_daily_qfq_single
from core.trade.rtfeed import fetch

TRAP_MIN = 60.0
BOT_LO, BOT_HI = 5.0, 20.0
TODAY = "20260908"


def chip_metrics(df, extra=None):
    """复用无门筹码口径: df 行尾可带今日近似bar(extra) 计算截至最后价的套牢/底部"""
    import pandas as pd
    if extra is not None:
        df = pd.concat([df, pd.DataFrame([extra])], ignore_index=False)
    ca = df["close"].values; la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    N = len(df)
    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    for j in range(max(0, N - 500), N):
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
    p = float(ca[-1])
    trap = float(c[bins > p].sum()) * 100
    bot = float(c[(bins >= p * .95) & (bins <= p * 1.05)].sum()) * 100
    lo20 = float(ca[-21:-1].min()) if N > 21 else float(ca.min())
    hi120 = float(ca[-121:-1].max()) if N > 121 else float(ca.max())
    return dict(trap=round(trap, 1), bot=round(bot, 1),
                dd20=round((p / lo20 - 1) * 100, 1) if lo20 else 0,
                dd120=round((p / hi120 - 1) * 100, 1) if hi120 else 0)


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    print(f"盘中近似扫描: {len(big)}只 ≥300亿 | 基准日 {TODAY} (腾讯实时)", flush=True)
    t0 = time.time()
    # 腾讯批量拿全池今日快照(分块)
    quotes = {}
    for i in range(0, len(big), 60):
        try:
            quotes.update(fetch(big[i:i + 60]))
        except Exception as e:
            print("  行情块失败", e, flush=True)
    print(f"拿到行情 {len(quotes)}/{len(big)} ({time.time()-t0:.0f}s)", flush=True)
    hits = []
    for ci, code in enumerate(big):
        q = quotes.get(code)
        if not q or q.get("high", 0) <= 0:
            continue
        try:
            df = fetch_daily_qfq_single(code, "2025-01-01", "2026-09-07")
            if df is None or len(df) < 250:
                continue
            last = df.iloc[-1]
            prev_turn = float(last["turnover"]) if "turnover" in df.columns else None
            prev_vol = float(last["volume"]) if "volume" in df.columns else None
            ratio = q["volume"] / prev_vol if prev_vol and prev_vol > 0 else 0.3
            turn = min(prev_turn * ratio if prev_turn else q.get("pct", 1) / 3, 40.0)
            extra = dict(date=pd_ts(TODAY), open=q["open"], high=q["high"],
                         low=q["low"], close=q["px"], volume=q["volume"],
                         turnover=turn)
            m = chip_metrics(df, extra)
            if m and m["trap"] >= TRAP_MIN and BOT_LO <= m["bot"] <= BOT_HI:
                m["code"] = code; m["name"] = q["name"]; m["px"] = q["px"]; m["pct"] = q["pct"]
                hits.append(m)
        except Exception:
            pass
        if (ci + 1) % 150 == 0:
            print(f"  {ci+1}/{len(big)}", flush=True)
    hits.sort(key=lambda x: (x["trap"] >= 80, -(20 - x["bot"]), x["trap"]), reverse=True)
    print(f"\n=== 盘中触发(近似) {len(hits)} 只 === 用时{time.time()-t0:.0f}s", flush=True)
    print(f"{'代码':<8}{'名称':<10}{'现价':>9}{'涨跌%':>8}{'套牢':>7}{'底部':>7}{'距20低':>8}{'距120高':>9}", flush=True)
    for m in hits[:30]:
        print(f"{m['code']:<8}{(m['name'][:5]+'..' if len(m['name'])>5 else m['name']):<10}"
              f"{m['px']:>9.2f}{m['pct']:>+7.2f}%{m['trap']:>6.1f}%{m['bot']:>6.1f}%"
              f"{m['dd20']:>+7.1f}%{m['dd120']:>+8.1f}%", flush=True)
    print("\n⚠️ 盘中近似(今日未收盘), 收盘后以正式扫描为准", flush=True)


def pd_ts(s):
    import pandas as pd
    return pd.to_datetime(s, format="%Y%m%d")


if __name__ == "__main__":
    main()
