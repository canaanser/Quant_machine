# -*- coding: utf-8 -*-
"""王文五双向闸门验证（2026-09-02 老板：300只没数据白扫，用王文五数据全的84只池）
样本：84只里 技术面合格 24 只（全有王文五 reports，闸门全生效）
配置：multi门 止盈30%，2025-01-01 空仓起步（同 out_of_sample 口径）
对比：无闸门 / ww_min=2 / ww_min=2+ww_exit=1
用法（Windows）：python -B scripts/verify_ww_gate.py
"""
import sys
import io
import json
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

    names = json.load(open(ROOT / 'data' / 'stock_names.json', encoding='utf-8'))
    codes = list(cfg.SCAN_TICKERS)
    have = [c for c in codes if (ROOT / 'data' / 'info' / 'fundamentals' / 'reports' / f'{c}.csv').exists()]
    md = load_data(source='freestockdb', tickers=have, start='2021-01-01',
                   end=END, frequency='1d', fq='qfq')
    TRAIN = pd.Timestamp('2024-12-31')
    # 技术面合格（同 out_of_sample）
    passed = []
    for code in have:
        px = md.price[code].dropna()
        pxt = px[px.index <= TRAIN]
        if len(pxt) < 60:
            continue
        ret20 = pxt / pxt.shift(20) - 1
        sig = ret20[ret20 < -0.20]
        if code in md.volume.columns:
            vol = md.volume[code].dropna()
            vr = vol / vol.shift(1).rolling(20).mean()
            sig = sig[vr.reindex(sig.index) > 0.7] if vr.reindex(sig.index).notna().any() else sig
        if len(sig) >= 10:
            px10 = pxt.shift(-10)
            fwd = px10.reindex(sig.index).dropna()
            spx = pxt.reindex(fwd.index)
            wr = (fwd > spx).sum() / len(fwd) if len(fwd) else 0
            if wr >= 0.65:
                passed.append(code)
    print(f"王文五数据全的技术面合格票: {len(passed)} 只")
    for c in passed:
        print(f"  {c} {names.get(c,'?')}")

    def run(tag, wwmin=None, wwexit=None):
        st = SimpleStrategy(5, 20)
        eng = BacktestPipeline(st, top_n=10, risk_config={}, verbose=False,
                               stop_loss_pct=None, take_profit_pct=0.30,
                               trend_gate='multi', ww_min=wwmin, ww_exit=wwexit)
        eng.trend_gate_threshold = 2
        with contextlib.redirect_stdout(io.StringIO()):
            eng.run(md_sub, initial_cash=500000, auto_save=False, trade_start=TEST_START)
        eq = eng.equity_curve
        seg = eq[eq.index >= pd.Timestamp(TEST_START)]
        r = seg.iloc[-1] / seg.iloc[0] - 1 if len(seg) > 60 else float('nan')
        dd = (seg / seg.cummax() - 1).min() if len(seg) > 60 else float('nan')
        tr = eng.trades
        tr25 = tr[pd.to_datetime(tr['Date']) >= pd.Timestamp(TEST_START)] if not tr.empty else tr
        print(f"[{tag}] 2025起收益 {r:+.1%} | 回撤 {dd:.1%} | Sharpe {eng.sharpe:.2f} | 交易{len(tr25)}", flush=True)

    md_sub = load_data(source='freestockdb', tickers=passed, start=START, end=END,
                       frequency='1d', fq='qfq')
    print("\n" + "=" * 60)
    print("王文五双向闸门对比（2025 空仓起步，multi门 止盈30%）")
    print("=" * 60)
    run("无闸门")
    run("ww_min=2 进场门槛", wwmin=2)
    run("ww_min=2 + ww_exit=1 双闸门", wwmin=2, wwexit=1)


if __name__ == '__main__':
    main()
