# -*- coding: utf-8 -*-
"""
双均线金叉（SimpleStrategy）84 只 10 年回测——单股买卖明细导出
================================================================
2026-08-28 小二陈：老板要客观的单股买卖数据（带名称/日期/价格），
分析"2026 年科技股大涨但账户没吃到红利"的现象。

输出：
  1. outputs/simple_trades_detail.csv —— 每笔交易明细（日期/代码/名称/方向/价格/数量/金额）
  2. outputs/simple_trades_stock_stats.csv —— 每只股票统计：
     交易笔数 / 策略累计实现盈亏(元) / 10年买入持有收益 / 2026年内策略盈亏 / 2026年内买入持有
  3. 控制台打印科技股 2026 年交易明细（重点看踏空）

用法（Windows，需 stockdb.exe 服务）：
    cd E:/stockgate/Quant_Alpha_System
    python scripts/dump_simple_trades.py
"""

import sys
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import pandas as pd
from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy
import config.config as config_mod

START, END = '2017-01-01', '2026-08-27'
INITIAL_CASH = 500000
DEFAULT_TICKERS = list(config_mod.SCAN_TICKERS)


def load_names() -> dict:
    p = PROJECT_ROOT / 'data' / 'stock_names.json'
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return {}


def stock_stats(g: pd.DataFrame, price: pd.Series, names: dict) -> dict:
    """按加权平均成本法配对买卖，算每只股票的策略实现盈亏 + 买入持有对比"""
    code = g['Stock'].iloc[0]
    avg_cost, shares, realized = 0.0, 0, 0.0
    trades_2026 = 0
    realized_2026 = 0.0
    for _, r in g.iterrows():
        if r['Action'] == 'BUY':
            total = shares + r['Shares']
            avg_cost = (avg_cost * shares + r['Price'] * r['Shares']) / total if total else r['Price']
            shares = total
            if r['Date'] >= '2026-01-01':
                trades_2026 += 1
        else:  # SELL
            pnl = (r['Price'] - avg_cost) * r['Shares']
            realized += pnl
            shares -= r['Shares']
            if r['Date'] >= '2026-01-01':
                trades_2026 += 1
                realized_2026 += pnl

    price = price.dropna()
    bh_10y = price.iloc[-1] / price.iloc[0] - 1 if len(price) > 1 else 0.0
    p26 = price[price.index >= '2026-01-01']
    bh_2026 = p26.iloc[-1] / p26.iloc[0] - 1 if len(p26) > 1 else 0.0

    return {
        '代码': code,
        '名称': names.get(code, '?'),
        '交易笔数': len(g),
        '策略盈亏_元': round(realized, 2),
        '10年买入持有': round(bh_10y, 4),
        '2026交易笔数': trades_2026,
        '2026策略盈亏_元': round(realized_2026, 2),
        '2026买入持有': round(bh_2026, 4),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Simple 回测单股买卖明细导出")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    names = load_names()

    t0 = time.time()
    print(f"🚀 回测中：{len(tickers)} 只，{args.start} ~ {args.end} ...")
    market_data = load_data(
        source='freestockdb', tickers=tickers,
        start=args.start, end=args.end, frequency='1d', fq='qfq'
    )
    engine = BacktestPipeline(SimpleStrategy(short=5, long=20, verbose=False), top_n=10, verbose=False)
    engine.run(market_data, initial_cash=INITIAL_CASH, auto_save=False)
    print(f"✅ 回测完成，耗时 {time.time() - t0:.1f}s，{len(engine.trades)} 笔交易")

    df = engine.trades
    if 'Date' not in df.columns:
        df = df.rename(columns={c: str(c).title() for c in df.columns})
    df['Date'] = df['Date'].astype(str).str[:10]
    df['名称'] = df['Stock'].map(names).fillna('?')
    df['金额'] = (df['Price'] * df['Shares']).round(2)

    out_dir = PROJECT_ROOT / 'outputs'
    detail_path = out_dir / 'simple_trades_detail.csv'
    df.to_csv(detail_path, index=False, encoding='utf-8-sig')
    print(f"💾 明细已存: {detail_path} ({len(df)} 行)")

    # 每只股票统计
    stats_rows = []
    for code, g in df.groupby('Stock'):
        stats_rows.append(stock_stats(g, market_data.price[code], names))
    stats = pd.DataFrame(stats_rows).sort_values('策略盈亏_元', ascending=False)
    stats_path = out_dir / 'simple_trades_stock_stats.csv'
    stats.to_csv(stats_path, index=False, encoding='utf-8-sig')
    print(f"💾 股票统计已存: {stats_path}")

    # 控制台：Top 盈亏 + 2026 踏空榜（10年涨得多但策略没吃到的）
    print("\n========== 策略盈亏 Top 15 ==========")
    print(stats[['代码', '名称', '交易笔数', '策略盈亏_元']].head(15).to_string(index=False))
    print("\n========== 策略盈亏 Bottom 10 ==========")
    print(stats[['代码', '名称', '交易笔数', '策略盈亏_元']].tail(10).to_string(index=False))
    print("\n========== 2026 踏空榜（10年/2026 涨得多，但策略没吃到）==========")
    gainers = stats[(stats['10年买入持有'] > 1.0) | (stats['2026买入持有'] > 0.3)].copy()
    gainers['踏空幅度'] = gainers['2026买入持有'] - gainers['2026策略盈亏_元'] / 500000
    print(gainers[['代码', '名称', '2026买入持有', '2026策略盈亏_元', '10年买入持有', '交易笔数']]
          .sort_values('2026买入持有', ascending=False).to_string(index=False))

    # 科技股 2026 交易明细
    tech_kw = ('科技', '通讯', '讯', '微', '信息', '电子', '光', '半导体', '浪潮', '精密')
    tech = stats[stats['名称'].apply(lambda n: any(k in n for k in tech_kw))]
    if len(tech):
        tech_codes = set(tech['代码'])
        detail_26 = df[(df['Stock'].isin(tech_codes)) & (df['Date'] >= '2026-01-01')]
        print("\n========== 科技股 2026 年交易明细 ==========")
        if len(detail_26):
            print(detail_26[['Date', 'Stock', '名称', 'Action', 'Price', 'Shares']].to_string(index=False))
        else:
            print("（2026 年内科技股无任何交易——完全踏空）")
    print("\n总账户: 累计收益", f"{engine.total_return:.2%}", " Sharpe", f"{engine.sharpe:.2f}",
          " 回撤", f"{engine.max_drawdown:.2%}")


if __name__ == "__main__":
    main()
