# -*- coding: utf-8 -*-
"""fetch_min_samples — 83只池 近N交易日 分钟K 缓存(做T离线学习用, 2026-09-10)
输入: outputs/pool83.json
输出: outputs/min_samples/<code>.csv  (date,open,high,low,close,volume,amount)
数据: 本地7899 http json "分钟k:<code>:<YYYYMMDD>*" 单请求=当日242根
用法: python -B scripts/fetch_min_samples.py [交易日数=10]
"""
import csv, json, sys, time, urllib.request, urllib.parse
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core" / "lib"))
BASE = "http://127.0.0.1:7899/?cmd=get&t={}&json=1"


def http_json(expr):
    with urllib.request.urlopen(BASE.format(urllib.parse.quote(expr)), timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def trade_dates(n):
    """取基准日K(000001)最近n个交易日YYYYMMDD"""
    from core.data_loader.freestockdb import fetch_daily_qfq_single
    df = fetch_daily_qfq_single("000001", "2026-08-10", "2026-12-31")
    ds = [int(str(d.date()).replace("-", "")) for d in df.index]
    return ds[-n:]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    codes = json.load(open(ROOT / "outputs/pool83.json", encoding="utf-8"))
    days = trade_dates(n)
    out = ROOT / "outputs/min_samples"
    out.mkdir(exist_ok=True)
    print(f"交易日数 {n} | 代码 {len(codes)} | 范围 {days[0]}..{days[-1]}", flush=True)
    for code in codes:
        fp = out / f"{code}.csv"
        new = False
        f = open(fp, "a", encoding="utf-8", newline="")
        w = csv.writer(f)
        if fp.stat().st_size == 0:
            w.writerow(["date", "open", "high", "low", "close", "volume", "amount"])
        for d in days:
            try:
                rows = http_json(f"分钟k:{code}:{d}*")
                for _, it in rows:
                    w.writerow([it["date"], it.get("open"), it.get("high"), it.get("low"),
                                it.get("close"), it.get("volume"), it.get("amount")])
                    new = True
            except Exception as e:
                print(f"  {code} {d} err {repr(e)[:60]}", flush=True)
            time.sleep(0.01)
        f.close()
        if new:
            print(f"  {code} ok", flush=True)
    print("DONE")


if __name__ == "__main__":
    main()
