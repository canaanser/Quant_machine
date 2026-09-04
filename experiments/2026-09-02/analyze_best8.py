# -*- coding: utf-8 -*-
"""
8只新票 最佳收益组合 买卖分析（2026-09-02 老板：赚钱/亏损归因）
============================================================
配置：multi≥2 门，无止损无止盈（= 全网格最优累计 +235.6%，Sharpe 0.92）
输出：① 每只票 盈亏/笔数/胜率 ② 赚最多/亏最多的票 ③ 总览
用法（Windows）：python -B scripts/analyze_best8.py
"""
import sys
import io
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

TICKERS = ['603019', '000977', '600160', '002050', '002837',
           '001979', '000786', '002791']


def fifo_pnl(trades: pd.DataFrame):
    """按票 FIFO 配对：BUY 入队列，SELL 与最早买入配对算盈亏（含佣金忽略）"""
    per_stock = {}
    for code in trades['Stock'].unique():
        sub = trades[trades['Stock'] == code].sort_values('Date')
        queue = []  # (shares, price)
        realized = []
        for _, t in sub.iterrows():
            if t['Action'] == 'BUY':
                queue.append((int(t['Shares']), float(t['Price'])))
            elif t['Action'] == 'SELL':
                remain = int(t['Shares'])
                sell_px = float(t['Price'])
                while remain > 0 and queue:
                    sh, buy_px = queue[0]
                    take = min(sh, remain)
                    realized.append((take, buy_px, sell_px))
                    remain -= take
                    if take == sh:
                        queue.pop(0)
                    else:
                        queue[0] = (sh - take, buy_px)
        per_stock[code] = realized
    return per_stock


def main():
    import logging as _logging
    _logging.disable(_logging.CRITICAL)
    from core.data_loader import load_data
    from core.backtest import BacktestPipeline
    from core.strategy import SimpleStrategy

    md = load_data(source='freestockdb', tickers=TICKERS, start='2022-06-01',
                   end='2026-08-27', frequency='1d', fq='qfq')
    st = SimpleStrategy(5, 20)
    eng = BacktestPipeline(st, top_n=10, risk_config={}, verbose=False,
                           stop_loss_pct=None, take_profit_pct=None, trend_gate='multi')
    eng.trend_gate_threshold = 2
    with contextlib.redirect_stdout(io.StringIO()):
        eng.run(md, initial_cash=500000, auto_save=False)

    print(f"📊 组合: multi门 无止损无止盈 | 累计 {eng.total_return:+.1%} | "
          f"Sharpe {eng.sharpe:.2f} | 回撤 {eng.max_drawdown:.1%}")
    eq = eng.equity_curve
    w1 = eq[eq.index >= (eq.index[-1] - pd.DateOffset(years=1))]
    w2 = eq[eq.index >= (eq.index[-1] - pd.DateOffset(years=2))]
    print(f"   近1年 {w1.iloc[-1]/w1.iloc[0]-1:+.1%} | 近2年 {w2.iloc[-1]/w2.iloc[0]-1:+.1%}")

    # 每票盈亏
    realized = fifo_pnl(eng.trades)
    names = pd.read_json(str(ROOT / 'data' / 'stock_names.json'), typ='series')
    rows = []
    for code in TICKERS:
        rl = realized.get(code, [])
        if not rl:
            rows.append({'代码': code, '名称': names.get(code, ''), '笔数': 0, '总盈亏': 0,
                         '胜率': None, '盈利笔': 0, '亏损笔': 0,
                         '平均盈%': None, '平均亏%': None, '最大盈%': None, '最大亏%': None})
            continue
        total_sh = sum(sh for sh, _, _ in rl)
        pnl_sum = sum(sh * (sell - buy) for sh, buy, sell in rl)
        pct = [(sell - buy) / buy for sh, buy, sell in rl]  # 每股收益率
        wins = [p for p in pct if p > 0]
        loss = [p for p in pct if p <= 0]
        rows.append({
            '代码': code, '名称': names.get(code, ''),
            '笔数': len(pct), '总盈亏': pnl_sum,
            '胜率': len(wins) / len(pct) if pct else None,
            '盈利笔': len(wins), '亏损笔': len(loss),
            '平均盈%': sum(wins) / len(wins) if wins else None,
            '平均亏%': sum(loss) / len(loss) if loss else None,
            '最大盈%': max(pct) if pct else None,
            '最大亏%': min(pct) if pct else None,
        })
    df = pd.DataFrame(rows).sort_values('总盈亏', ascending=False)
    print("\n===== 每只票盈亏归因（按总盈亏降序）=====")
    print(f"{'代码':8s}{'名称':8s}{'笔数':>5s}{'总盈亏':>10s}{'胜率':>7s}{'盈':>4s}{'亏':>4s}"
          f"{'平均盈%':>8s}{'平均亏%':>8s}{'最大盈%':>8s}{'最大亏%':>8s}")
    for _, r in df.iterrows():
        print(f"{r['代码']:8s}{str(r['名称']):8s}{int(r['笔数']):>5d}{r['总盈亏']:>+10.0f}"
              f"{(r['胜率'] or 0):>7.0%}{int(r['盈利笔']):>4d}{int(r['亏损笔']):>4d}"
              f"{(r['平均盈%'] or 0):>+8.1%}{(r['平均亏%'] or 0):>+8.1%}"
              f"{(r['最大盈%'] or 0):>+8.1%}{(r['最大亏%'] or 0):>+8.1%}")

    # 每只票最大单笔盈亏记录（最好/最差的交易）
    print("\n===== 每只票 最赚一笔 / 最亏一笔 =====")
    for _, r in df.iterrows():
        if r['笔数'] == 0:
            continue
        code = r['代码']
        rl = realized[code]
        best = max(rl, key=lambda x: (x[2] - x[1]) / x[1])
        worst = min(rl, key=lambda x: (x[2] - x[1]) / x[1])
        print(f"  {code} {r['名称']:6s} 最赚: {best[2]:.2f} vs {best[1]:.2f} 买 "
              f"({(best[2]-best[1])/best[1]:+.1%}) | 最亏: {worst[2]:.2f} vs {worst[1]:.2f} 买 "
              f"({(worst[2]-worst[1])/worst[1]:+.1%})")

    total_pnl = df['总盈亏'].sum()
    print(f"\n===== 总览 =====")
    print(f"  合计平仓盈亏: {total_pnl:+,.0f} 元（初始 500,000 → 期末约 "
          f"{500000 * (1 + eng.total_return):,.0f}）")
    print(f"  盈利票 {len(df[df['总盈亏'] > 0])} 只 | 亏损票 {len(df[df['总盈亏'] < 0])} 只 | "
          f"无交易 {len(df[df['笔数'] == 0])} 只")


if __name__ == '__main__':
    main()
