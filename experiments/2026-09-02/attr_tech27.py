# -*- coding: utf-8 -*-
"""技术面合格 27 只 逐票归因（2026-09-02 老板：验证 +208% 是不是押中几只大牛）
配置：multi门 无止损，2025-01-01 空仓起步（与 out_of_sample 实测一致）
输出：① 27只名单 ② 每票2025起贡献 ③ 收益集中度（top3占多少）
用法（Windows）：python -B scripts/attr_tech27.py
"""
import sys
import io
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

START, END = '2021-01-01', '2026-08-27'
TEST_START = '2025-01-01'


def main():
    import logging as _logging
    _logging.disable(_logging.CRITICAL)
    from core.data_loader import load_data
    from core.backtest import BacktestPipeline
    from core.strategy import SimpleStrategy
    import config.config as cfg

    # 复算训练期技术面合格（与 out_of_sample 同逻辑）
    from selection.wangwen import WangwenSelector
    import importlib
    oos = importlib.import_module('out_of_sample') if False else None
    # 直接内联判定：技术面=深跌放量信号>=10 且 胜率>=65%（2024-12-31前）
    names = pd.read_json(str(ROOT / 'data' / 'stock_names.json'), typ='series')
    all_codes = list(cfg.SCAN_TICKERS)
    md_full = load_data(source='freestockdb', tickers=all_codes, start='2021-01-01',
                        end=END, frequency='1d', fq='qfq')
    TRAIN = pd.Timestamp('2024-12-31')

    tech_pass = []
    for code in all_codes:
        px = md_full.price[code].dropna()
        px = px[px.index <= TRAIN]
        if len(px) < 60:
            continue
        ret20 = px / px.shift(20) - 1
        signals = ret20[ret20 < -0.20]
        vol = md_full.volume[code].dropna() if code in md_full.volume.columns else None
        if vol is not None:
            vr = vol / vol.shift(1).rolling(20).mean()
            vv = vr.reindex(signals.index)
            signals = signals[vv > 0.7] if vv.notna().any() else signals
        if len(signals) < 5:
            continue
        px10 = px.shift(-10)
        fwd = px10.reindex(signals.index).dropna()
        sig_px = px.reindex(fwd.index)
        wins = (fwd > sig_px).sum()
        wr = wins / len(fwd) if len(fwd) else 0
        if len(signals) >= 10 and wr >= 0.65:
            tech_pass.append((code, len(signals), wr))
    tech_codes = [c for c, _, _ in tech_pass]
    print(f"技术面合格 {len(tech_codes)} 只:")
    for c, n, wr in sorted(tech_pass, key=lambda x: -x[2]):
        print(f"  {c} {names.get(c,'?'):6s} 信号{n}次 胜率{wr:.0%}")

    # 逐票 2025 空仓起步归因（每票单独跑，看谁贡献）
    print("\n===== 逐票 2025 空仓起步（单票 multi门，看独立表现）=====")
    rows = []
    for code in tech_codes:
        try:
            sub = load_data(source='freestockdb', tickers=[code], start=START,
                            end=END, frequency='1d', fq='qfq')
            st = SimpleStrategy(5, 20)
            eng = BacktestPipeline(st, top_n=10, risk_config={}, verbose=False,
                                   stop_loss_pct=None, take_profit_pct=None, trend_gate='multi')
            eng.trend_gate_threshold = 2
            with contextlib.redirect_stdout(io.StringIO()):
                eng.run(sub, initial_cash=500000, auto_save=False, trade_start=TEST_START)
            eq = eng.equity_curve
            seg = eq[eq.index >= pd.Timestamp(TEST_START)]
            r = seg.iloc[-1] / seg.iloc[0] - 1 if len(seg) > 60 else float('nan')
            rows.append({'code': code, 'name': names.get(code, '?'), 'ret': r,
                         'trades': len(eng.trades)})
        except Exception as e:
            rows.append({'code': code, 'name': names.get(code, '?'), 'ret': float('nan'), 'trades': -1})
    df = pd.DataFrame(rows).sort_values('ret', ascending=False)
    print(f"{'代码':<7}{'名称':<8}{'2025起收益':>10}{'交易':>6}")
    for _, r in df.iterrows():
        rr = f"{r['ret']:+.1%}" if r['ret'] == r['ret'] else 'NA'
        print(f"{r['code']:<7}{r['name']:<8}{rr:>10}{int(r['trades']):>6}")
    pos = df[df['ret'] > 0]
    neg = df[df['ret'] < 0]
    print(f"\n正收益 {len(pos)} 只 | 负收益 {len(neg)} 只")
    if len(pos) >= 3:
        top3 = pos.nlargest(3, 'ret')
        tot_pos = pos['ret'].sum()
        print(f"top3 ({', '.join(top3['name'])}) 合计 {top3['ret'].sum():+.0%} / 正收益总和 {tot_pos:+.0%} "
              f"= 占比 {top3['ret'].sum()/tot_pos:.0%}")


if __name__ == '__main__':
    main()
