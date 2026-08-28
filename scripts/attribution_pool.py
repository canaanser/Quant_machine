# -*- coding: utf-8 -*-
"""
股票池归因分析（2026-08-29 小二陈）：买入的每只票归因
================================================================
老板要求：84只 vs 精选15只差距的原因——每只票贡献归因。
对每只票（加权平均成本法配对买卖）：
  买入笔数/卖出笔数、实现盈亏(元)、胜率、平均持有天数、期末持仓盈亏、贡献占比
输出：贡献正负排名——找出赚钱主力 + 回撤元凶。

用法（Windows，python -B）：
    python -B scripts/attribution_pool.py                    # 84只 建仓
    python -B scripts/attribution_pool.py --mode 进攻        # 84只 进攻
    python -B scripts/attribution_pool.py --tickers 002156,600522  # 自定义
"""
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / 'pybao') not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / 'pybao'))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import pandas as pd
from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy
from config.risk_config import DEFAULT_RISK_CONFIG
import config.config as config_mod
import copy


def load_names() -> dict:
    p = PROJECT_ROOT / 'data' / 'stock_names.json'
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return {}


def attribute_stock(g: pd.DataFrame, price: pd.Series, names: dict) -> dict:
    """单只票归因：加权平均成本配对买卖，算实现盈亏/胜率/持有天数"""
    code = g['Stock'].iloc[0]
    avg_cost, shares = 0.0, 0
    realized, wins, sells = 0.0, 0, 0
    hold_days, hold_cnt = 0, 0
    buy_dates = []
    for _, r in g.iterrows():
        if r['Action'] == 'BUY':
            total = shares + r['Shares']
            avg_cost = (avg_cost * shares + r['Price'] * r['Shares']) / total if total else r['Price']
            shares = total
            buy_dates.append(r['Date'])
        else:  # SELL
            pnl = (r['Price'] - avg_cost) * r['Shares']
            realized += pnl
            shares -= r['Shares']
            sells += 1
            if pnl > 0:
                wins += 1
            if buy_dates:
                hold_days += (r['Date'] - buy_dates[0]).days
                hold_cnt += 1
                buy_dates.pop(0)
    # 期末持仓盈亏（未实现）
    unrealized = 0.0
    if shares > 0 and len(price.dropna()) > 0:
        last_px = price.dropna().iloc[-1]
        unrealized = (last_px - avg_cost) * shares
    return {
        '代码': code, '名称': names.get(code, '?'),
        '买入笔数': len(g[g['Action'] == 'BUY']),
        '卖出笔数': sells,
        '实现盈亏': round(realized, 0),
        '胜率': round(wins / sells, 2) if sells else None,
        '平均持有(天)': round(hold_days / hold_cnt) if hold_cnt else None,
        '期末浮盈': round(unrealized, 0),
        '总贡献': round(realized + unrealized, 0),
    }


def main():
    import argparse
    import logging
    parser = argparse.ArgumentParser(description="股票池归因分析")
    parser.add_argument("--tickers", default=",".join(config_mod.SCAN_TICKERS))
    parser.add_argument("--mode", default='建仓', choices=['建仓', '进攻'])
    parser.add_argument("--only", default="", help="只打印指定代码的每笔买卖记录（如 000657）")
    parser.add_argument("--start", default='2017-01-01')
    parser.add_argument("--end", default='2026-08-27')
    args = parser.parse_args()

    logging.disable(logging.INFO)  # 静默中间日志（老板要求最终表集中）

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    names = load_names()

    print(f"🚀 归因回测：{len(tickers)} 只，{args.start} ~ {args.end}，模式「{args.mode}」...")
    md = load_data(source='freestockdb', tickers=tickers,
                   start=args.start, end=args.end, frequency='1d', fq='qfq')
    rc = copy.deepcopy(DEFAULT_RISK_CONFIG)
    if args.mode == '建仓':
        rc.update({'MAX_SINGLE_POSITION_RATIO': 0.10, 'BASE_POSITION_RATIO': 0.20})
        sl, batch, protect = 0.05, True, 2
    else:
        rc.update({'MAX_SINGLE_POSITION_RATIO': 0.30, 'BASE_POSITION_RATIO': 0.50})
        sl, batch, protect = 0.08, True, 0
    strategy = SimpleStrategy(5, 20, quality_filter=True, quality_penalty=0.1, bottom_confirm=True)
    engine = BacktestPipeline(strategy, top_n=10, risk_config=rc, verbose=False,
                              stop_loss_pct=sl, batch_exit=batch, protect_days=protect)
    engine.run(md, initial_cash=500000, auto_save=False)
    print(f"✅ 回测完成：累计 {engine.total_return:.2%} / Sharpe {engine.sharpe:.2f} / 回撤 {engine.max_drawdown:.2%} / {len(engine.trades)} 笔")

    df = engine.trades
    df['Date'] = pd.to_datetime(df['Date'])
    df['Stock'] = df['Stock'].astype(str)

    # 每只票归因
    rows = []
    for code, g in df.groupby('Stock'):
        price = md.price[code] if code in md.price.columns else pd.Series(dtype=float)
        rows.append(attribute_stock(g, price, names))
    att = pd.DataFrame(rows).sort_values('总贡献', ascending=False)

    print("\n" + "=" * 78)
    print(f"📊 股票池归因（{args.mode}，{len(tickers)} 只，共 {len(df)} 笔交易）")
    print("=" * 78)
    print(f"{'代码':<8}{'名称':<8}{'买入':>5}{'卖出':>5}{'实现盈亏':>12}{'胜率':>6}{'持有天':>7}{'期末浮盈':>12}{'总贡献':>12}")
    print("-" * 78)
    for _, r in att.iterrows():
        win = f"{r['胜率']:.0%}" if pd.notna(r['胜率']) else "-"
        hold = f"{r['平均持有(天)']}" if pd.notna(r['平均持有(天)']) else "-"
        print(f"{r['代码']:<8}{r['名称']:<8}{r['买入笔数']:>5}{r['卖出笔数']:>5}"
              f"{r['实现盈亏']:>12,.0f}{win:>6}{hold:>7}{r['期末浮盈']:>12,.0f}{r['总贡献']:>12,.0f}")
    print("=" * 78)
    # 只打印指定票的买卖记录，每笔带盈亏（加权平均成本配对，老板 2026-08-29 要每买每卖挣多少）
    if args.only:
        code = args.only
        g = df[df['Stock'] == code]
        nm = names.get(code, '?')
        avg_cost, shares, cum_pnl = 0.0, 0, 0.0
        print(f"\n📊 {code} {nm} 买卖记录（共 {len(g)} 笔）——卖出行显示该笔盈亏 + 累计盈亏")
        print(f"{'日期':<12}{'操作':<5}{'价格':>9}{'数量':>7}{'成本':>8}{'该笔盈亏':>12}{'累计盈亏':>12}{'剩余':>6}")
        print("-" * 82)
        for _, r in g.iterrows():
            px = float(r['Price']); qty = int(r['Shares'])
            if r['Action'] == 'BUY':
                total = shares + qty
                avg_cost = (avg_cost * shares + px * qty) / total if total else px
                shares = total
                print(f"{str(r['Date'])[:10]:<12}{'BUY':<5}{px:>9.2f}{qty:>7}{avg_cost:>8.2f}{'':>12}{'':>12}{shares:>6}")
            else:
                pnl = (px - avg_cost) * qty
                cum_pnl += pnl
                shares -= qty
                print(f"{str(r['Date'])[:10]:<12}{'SELL':<5}{px:>9.2f}{qty:>7}{avg_cost:>8.2f}{pnl:>12,.0f}{cum_pnl:>12,.0f}{shares:>6}")
        print("=" * 82)
        # 分年度汇总（老板 2026-08-29：要看每年代实现盈亏 + 总盈亏）
        g['Year'] = g['Date'].dt.year
        yearly = []
        for yr, yg in g.groupby('Year'):
            avg_c, sh, realized = 0.0, 0, 0.0
            for _, rr in yg.iterrows():
                if rr['Action'] == 'BUY':
                    t = sh + rr['Shares']
                    avg_c = (avg_c * sh + rr['Price'] * rr['Shares']) / t if t else rr['Price']
                    sh = t
                else:
                    realized += (rr['Price'] - avg_c) * rr['Shares']
                    sh -= rr['Shares']
            yearly.append((yr, realized))
        print(f"\n📅 {code} {nm} 分年度实现盈亏（总 {cum_pnl:,.0f} 元）")
        for yr, rl in yearly:
            print(f"  {yr}: {rl:>+12,.0f} 元")
        print("=" * 82)
        return
    # 汇总
    pos_sum = att[att['总贡献'] > 0]['总贡献'].sum()
    neg_sum = att[att['总贡献'] < 0]['总贡献'].sum()
    print(f"✅ 正贡献合计: {pos_sum:,.0f} 元（{len(att[att['总贡献']>0])} 只）")
    print(f"❌ 负贡献合计: {neg_sum:,.0f} 元（{len(att[att['总贡献']<0])} 只）——回撤/亏损元凶")


if __name__ == "__main__":
    main()
