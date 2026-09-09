# -*- coding: utf-8 -*-
"""分时图绘制入口（2026-09-06 老板：分时图=折线不是蜡烛）

用法（Windows / WSL 均可，本地 stockdb）：
    python -B scripts/plot_fenshi.py --code 000063 --date 2026-07-21
    python -B scripts/plot_fenshi.py --code 000063 --date 2026-07-21 --out outputs/zte_0721.html
    python -B scripts/plot_fenshi.py --code 603606 --date 2026-09-02 --name 东方电缆
说明：分时价白线、均价黄线（累计额/累计量）、昨收灰虚线、下挂量柱。游标悬停读值。
"""
import sys
import json
import argparse
import urllib.request
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from core.lib.utils.kline_plotter import plot_fenshi

HOST = "127.0.0.1:7899"
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get(expr: str):
    url = f"http://{HOST}/?cmd=get&t={urllib.parse.quote(expr)}"
    with _opener.open(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_minute(code: str, day: str):
    """某日全天分钟K → DataFrame(open/high/low/close/amount/volume)"""
    code = "".join(c for c in code if c.isdigit())[:6].zfill(6)
    rows = http_get(f"分钟k:{code}:{day}*")
    if not rows:
        return None
    bars = [r[1] for r in rows]
    df = pd.DataFrame(bars)
    df["t"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d%H%M%S")
    df = df.set_index("t").sort_index()
    for col in ("open", "high", "low", "close", "amount", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def prev_close(code: str, day: str) -> float:
    """上一交易日收盘（当日 minute 表里第一根的 pre_close 或查日K）"""
    code = "".join(c for c in code if c.isdigit())[:6].zfill(6)
    y = day[:4]
    rows = http_get(f"日k:{code}:{y}*")
    ds = [r[1] for r in rows if str(r[1].get("date")) < day]
    if ds:
        return float(ds[-1]["close"])
    return None


def main():
    ap = argparse.ArgumentParser(description="分时图绘制（东方财富样式）")
    ap.add_argument("--code", required=True, help="6位代码")
    ap.add_argument("--date", required=True, help="日期 YYYY-MM-DD 或 YYYYMMDD")
    ap.add_argument("--name", default="", help="股票名称（显示用）")
    ap.add_argument("--out", default=None, help="输出 html 路径（默认 outputs/{code}_{date}_fenshi.html）")
    args = ap.parse_args()

    code = "".join(c for c in args.code if c.isdigit())[:6].zfill(6)
    day = args.date.replace("-", "")
    df = load_minute(code, day)
    if df is None or df.empty:
        print(f"❌ {code} {day} 无分钟数据")
        return
    pc = prev_close(code, day)
    out = args.out or str(PROJECT_ROOT / "outputs" / f"{code}_{day}_fenshi.html")
    fig = plot_fenshi(df, code, args.name, prev_close=pc)
    fig.write_html(out)
    print(f"✅ 已生成: {out}")
    print(f"   昨收 {pc:.2f} | 当日最低 {df['low'].min():.2f} | 收 {df['close'].iloc[-1]:.2f}")


if __name__ == "__main__":
    main()
