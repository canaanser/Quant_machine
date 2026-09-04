# -*- coding: utf-8 -*-
"""双过交集票 盈亏归因（2026-09-02 老板：看选出来的票到底谁赚谁亏）
配置：与 out_of_sample 实测一致（multi门 无止损），2021起全历史跑，2025起窗口重点看
用法（Windows）：python -B scripts/attr_oos_picks.py
"""
import sys
import io
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

TICKERS = ['300570', '688205', '600487', '600522', '000858', '300285', '301379']  # 双过交集7只
FOCUS = ['301379', '300285', '600487', '600522', '000858']  # 老板点名5只
START, END = '2021-01-01', '2026-08-27'


def main():
    import logging as _logging
    _logging.disable(_logging.CRITICAL)
    from core.data_loader import load_data
    from core.backtest import BacktestPipeline
    from core.strategy import SimpleStrategy

    md = load_data(source='freestockdb', tickers=TICKERS, start=START, end=END,
                   frequency='1d', fq='qfq')
    st = SimpleStrategy(5, 20)
    eng = BacktestPipeline(st, top_n=10, risk_config={}, verbose=False,
                           stop_loss_pct=None, take_profit_pct=None, trend_gate='multi')
    eng.trend_gate_threshold = 2
    with contextlib.redirect_stdout(io.StringIO()):
        eng.run(md, initial_cash=500000, auto_save=False)

    print(f"📊 双过交集7只 multi门无止损 | 全区间 {eng.total_return:+.1%}")
    df = eng.trades.copy()
    df['Date'] = pd.to_datetime(df['Date'])
    df['Stock'] = df['Stock'].astype(str)
    names = pd.read_json(str(ROOT / 'data' / 'stock_names.json'), typ='series')

    # 每票归因（加权成本 + 期末浮盈），分 全区间 / 2025起 两窗口
    def attr_stock(code, g, start_cut=None):
        if start_cut is not None:
            g = g[g['Date'] >= pd.Timestamp(start_cut)]
        if g.empty:
            return None
        avg_cost, shares = 0.0, 0
        realized, sells = 0.0, 0
        for _, r in g.iterrows():
            if r['Action'] == 'BUY':
                total = shares + r['Shares']
                avg_cost = (avg_cost * shares + r['Price'] * r['Shares']) / total if total else r['Price']
                shares = total
            else:
                realized += (r['Price'] - avg_cost) * r['Shares']
                shares -= r['Shares']
                sells += 1
        unrealized = 0.0
        # 期末价：2025起窗口用最后交易日价
        if shares > 0 and code in md.price.columns:
            last_px = md.price[code].dropna().iloc[-1]
            unrealized = (last_px - avg_cost) * shares
        return {'买入': int(len(g[g['Action'] == 'BUY'])), '卖出': sells,
                '实现': round(realized), '浮盈': round(unrealized),
                '总': round(realized + unrealized)}

    print("\n===== 每票盈亏（全区间 2021~2026）=====")
    print(f"{'代码':<7}{'名称':<8}{'买入':>5}{'卖出':>5}{'实现盈亏':>12}{'期末浮盈':>12}{'总贡献':>12}")
    for code in TICKERS:
        g = df[df['Stock'] == code]
        a = attr_stock(code, g)
        if not a:
            print(f"{code:<7}{names.get(code,'?'):<8}  无交易")
            continue
        print(f"{code:<7}{names.get(code,'?'):<8}{a['买入']:>5}{a['卖出']:>5}"
              f"{a['实现']:>12,.0f}{a['浮盈']:>12,.0f}{a['总']:>12,.0f}")

    print("\n===== 2025起 盈亏（样本外窗口，重点）=====")
    print(f"{'代码':<7}{'名称':<8}{'买入':>5}{'卖出':>5}{'实现盈亏':>12}{'期末浮盈':>12}{'总贡献':>12}")
    for code in FOCUS:
        g = df[df['Stock'] == code]
        a = attr_stock(code, g, '2025-01-01')
        if not a:
            print(f"{code:<7}{names.get(code,'?'):<8}  2025起无交易")
            continue
        print(f"{code:<7}{names.get(code,'?'):<8}{a['买入']:>5}{a['卖出']:>5}"
              f"{a['实现']:>12,.0f}{a['浮盈']:>12,.0f}{a['总']:>12,.0f}")

    # 每只票 2025 起的最大单笔盈亏
    print("\n===== 2025起 最赚/最亏一笔 =====")
    for code in FOCUS:
        g = df[(df['Stock'] == code) & (df['Date'] >= pd.Timestamp('2025-01-01'))].sort_values('Date')
        if g.empty:
            continue
        avg_cost, shares = 0.0, 0
        trades_pct = []
        for _, r in g.iterrows():
            if r['Action'] == 'BUY':
                total = shares + r['Shares']
                avg_cost = (avg_cost * shares + r['Price'] * r['Shares']) / total if total else r['Price']
                shares = total
            else:
                pct = (r['Price'] - avg_cost) / avg_cost if avg_cost else 0
                trades_pct.append((r['Date'], avg_cost, r['Price'], pct))
                shares -= r['Shares']
        if trades_pct:
            best = max(trades_pct, key=lambda x: x[3])
            worst = min(trades_pct, key=lambda x: x[3])
            print(f"  {code} {names.get(code,'?'):6s} 最赚 {best[2]:.2f}vs{best[1]:.2f}买({best[3]:+.1%}) "
                  f"| 最亏 {worst[2]:.2f}vs{worst[1]:.2f}买({worst[3]:+.1%})")


if __name__ == '__main__':
    main()
