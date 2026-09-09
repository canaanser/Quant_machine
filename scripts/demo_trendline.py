# -*- coding: utf-8 -*-
"""
趋势线 demo（2026-08-30 老板：趋势线跟随我们的图表，画出来看）
================================================================
用我们自己的数据源（freestockdb）+ 我们自己的画图（utils/kline_plotter）：
  1. 加载 K 线（OHLCV）
  2. core/trendline 检测趋势线（fractal 摆动点 + 三点确认）
  3. plot_kline_with_trades 叠加趋势线出图 → outputs/*.html

用法：
    python -B scripts/demo_trendline.py                 # 默认 000063 中兴
    python -B scripts/demo_trendline.py --tickers 000657,000063 --lookback 500
"""
import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from core.data_loader import load_data
from core.features.trendline import detect_trendlines
from core.lib.utils.kline_plotter import plot_kline_with_trades

OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'outputs')


def build_ohlc(md, code):
    """把 metadata 里 price/open/high/low/volume 合成 OHLCV DataFrame"""
    df = pd.DataFrame({'close': md.price[code]})
    if code in md.open_price.columns:
        df['open'] = md.open_price[code]
    if code in md.high_price.columns:
        df['high'] = md.high_price[code]
    if code in md.low_price.columns:
        df['low'] = md.low_price[code]
    if code in md.volume.columns:
        df['volume'] = md.volume[code]
    df = df.dropna(subset=['close']).copy()
    for col in ['open', 'high', 'low', 'volume']:
        if col not in df.columns:
            df[col] = df['close'] if col != 'volume' else 0
    # 补全 OHLC 缺失（用 close 近似）
    df['open'] = df['open'].fillna(df['close'])
    df['high'] = df['high'].fillna(df['close'])
    df['low'] = df['low'].fillna(df['close'])
    return df


def main():
    parser = argparse.ArgumentParser(description="趋势线 demo")
    parser.add_argument("--tickers", default="000063",
                        help="股票代码，逗号分隔（默认 000063 中兴通讯）")
    parser.add_argument("--start", default="2024-01-01", help="起始日期")
    parser.add_argument("--end", default="2026-08-27", help="结束日期")
    parser.add_argument("--touch", type=float, default=0.015,
                        help="触碰容差（默认 0.015=1.5%%）")
    parser.add_argument("--min-touches", type=int, default=3,
                        help="最少触碰点数（含两端，默认 3=两点定线第三点确认）")
    parser.add_argument("--k", type=int, default=5, help="fractal 摆动点窗口（默认 5）")
    parser.add_argument("--min-span", type=int, default=20,
                        help="两锚点最小跨度（根K线，默认 20）")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"🚀 加载 {len(tickers)} 只: {args.start} ~ {args.end} ...")
    md = load_data(source='freestockdb', tickers=tickers,
                   start=args.start, end=args.end, frequency='1d', fq='qfq')
    print(f"✅ 加载完成: {md.price.shape[0]} 交易日")

    # 名称（我们自己的 stock_names.json）
    names = {}
    try:
        import json
        with open(os.path.join(PROJECT_ROOT, 'data', 'stock_names.json'), 'r', encoding='utf-8') as f:
            names = json.load(f)
    except Exception:
        pass

    for code in tickers:
        code = str(code).zfill(6)
        if code not in md.price.columns:
            print(f"⚠️ {code} 无数据，跳过")
            continue
        ohlc = build_ohlc(md, code)
        if len(ohlc) < 60:
            print(f"⚠️ {code} 数据不足 60 根，跳过")
            continue

        tls = detect_trendlines(ohlc, k=args.k, touch_pct=args.touch,
                                min_touches=args.min_touches, min_span=args.min_span)
        print(f"\n📈 {code} {names.get(code, '')}: 检测到 {len(tls)} 条趋势线")
        for tl in tls:
            kind = "上升(支撑)" if tl['type'] == 'up' else "下降(压力)"
            print(f"   {kind} 斜率={tl['slope']:+.4f} 触碰={tl['touches']}点 "
                  f"锚点[{tl['x0']}→{tl['x1']}] 延伸至末行{tl['x_end']} 线值={tl['y_end']:.2f}")

        fig = plot_kline_with_trades(ohlc, trades_df=None,
                                     stock_code=code, stock_name=names.get(code, ''),
                                     trendlines=tls)
        # 图名带上趋势线信息
        fig.update_layout(title=f"{code} {names.get(code, '')} 趋势线（{len(tls)}条）")
        out = os.path.join(OUTPUT_DIR, f"trendline_{code}.html")
        fig.write_html(out)
        print(f"💾 已保存: {out}")


if __name__ == "__main__":
    main()
