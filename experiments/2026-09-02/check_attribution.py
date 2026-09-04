# -*- coding: utf-8 -*-
"""归因自检+重跑（2026-09-02 老板：不看文件，脚本自查配置并打印归因结果）
作用：打印 ①脚本版本标记 ②实际生效配置 ③归因回测结果——贴回来即可定位问题
用法（Windows）：python -B scripts/check_attribution.py
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


def main():
    import logging as _logging
    _logging.disable(_logging.CRITICAL)
    import copy
    from core.data_loader import load_data
    from core.backtest import BacktestPipeline
    from core.strategy import SimpleStrategy
    from config.risk_config import DEFAULT_RISK_CONFIG

    # ① 版本自检
    src = (ROOT / 'scripts' / 'attribution_pool.py').read_text(encoding='utf-8')
    print("① 脚本自检:")
    print(f"   attribution_pool.py 含 --no-quality: {'--no-quality' in src}")
    print(f"   含 --gate: {'--gate' in src}")
    print(f"   含 trend_gate=gate: {'trend_gate=gate' in src}")

    # ② 配置（与 scan_stopmatrix 最佳组合一致：multi门 无止损无止盈 无质量）
    print("\n② 生效配置:")
    print(f"   策略: SimpleStrategy(5,20) quality=OFF bottom=OFF")
    print(f"   风控: 无止损 无止盈 无分批 无保护期")
    print(f"   趋势门: multi(阈值≥2)  初始资金 500,000")
    print(f"   区间: 2022-06-01 ~ 2026-08-27")

    md = load_data(source='freestockdb', tickers=TICKERS, start='2022-06-01',
                   end='2026-08-27', frequency='1d', fq='qfq')
    print(f"   数据: {md.price.shape[0]} 交易日 × {md.price.shape[1]} 只")

    rc = copy.deepcopy(DEFAULT_RISK_CONFIG)
    st = SimpleStrategy(5, 20, quality_filter=False, bottom_confirm=False)
    eng = BacktestPipeline(st, top_n=10, risk_config=rc, verbose=False,
                           stop_loss_pct=None, take_profit_pct=None,
                           batch_exit=False, protect_days=0, trend_gate='multi')
    eng.trend_gate_threshold = 2
    with contextlib.redirect_stdout(io.StringIO()):
        eng.run(md, initial_cash=500000, auto_save=False)

    print("\n③ 回测结果:")
    print(f"   累计 {eng.total_return:+.2%} / Sharpe {eng.sharpe:.2f} / "
          f"回撤 {eng.max_drawdown:.2%} / 交易 {len(eng.trades)} 笔")
    buys = eng.trades[eng.trades['Action'] == 'BUY'] if not eng.trades.empty else pd.DataFrame()
    traded = sorted(buys['Stock'].unique()) if not buys.empty else []
    print(f"   实际买入票数: {len(traded)} 只 -> {traded}")

    # ④ 归因（加权成本 + 期末浮盈，复用 attribution_pool 逻辑）
    names = pd.read_json(str(ROOT / 'data' / 'stock_names.json'), typ='series')
    df = eng.trades.copy()
    df['Date'] = pd.to_datetime(df['Date'])
    df['Stock'] = df['Stock'].astype(str)

    def attr_stock(g):
        code = g['Stock'].iloc[0]
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
        if shares > 0 and code in md.price.columns:
            last_px = md.price[code].dropna().iloc[-1]
            unrealized = (last_px - avg_cost) * shares
        return {'代码': code, '名称': names.get(code, '?'),
                '买入': len(g[g['Action'] == 'BUY']), '卖出': sells,
                '实现盈亏': round(realized), '期末浮盈': round(unrealized),
                '总贡献': round(realized + unrealized)}

    print("\n④ 归因（含期末浮盈，按总贡献降序）:")
    rows = []
    for code, g in df.groupby('Stock'):
        rows.append(attr_stock(g))
    att = pd.DataFrame(rows).sort_values('总贡献', ascending=False)
    print(f"{'代码':<8}{'名称':<8}{'买入':>5}{'卖出':>5}{'实现盈亏':>11}{'期末浮盈':>11}{'总贡献':>11}")
    for _, r in att.iterrows():
        print(f"{r['代码']:<8}{str(r['名称']):<8}{int(r['买入']):>5}{int(r['卖出']):>5}"
              f"{r['实现盈亏']:>11,.0f}{r['期末浮盈']:>11,.0f}{r['总贡献']:>11,.0f}")
    pos = att[att['总贡献'] > 0]['总贡献'].sum()
    neg = att[att['总贡献'] < 0]['总贡献'].sum()
    print(f"✅ 正贡献合计: {pos:,.0f} 元（{len(att[att['总贡献']>0])} 只）")
    print(f"❌ 负贡献合计: {neg:,.0f} 元（{len(att[att['总贡献']<0])} 只）")


if __name__ == '__main__':
    main()
