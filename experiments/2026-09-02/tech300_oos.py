# -*- coding: utf-8 -*-
"""
300只随机池 技术面筛选 + 样本外实测（2026-09-02 老板：放大池子验证技术面选票）
=====================================================================
训练期（2024-12-31 视角，只用当日可见数据）：
  技术面：2021~2024 K线 深跌+放量信号 ≥10次 且 10日胜率 ≥65%（王文五财报暂停，等接口恢复）
实测期（2025-01-01 空仓起步，multi门 无止损 止盈30%——已验证最优控制）：
  筛出组 vs 随机未筛出组 vs 全300对照
用法（Windows）：python -B scripts/tech300_oos.py [--train-only]
"""
import sys
import io
import json
import random
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

TICKER_FILE = ROOT / 'data' / 'tickers' / 'tech300_seed99.txt'
TRAIN_DATE = '2024-12-31'
TEST_START = '2025-01-01'
START, END = '2021-01-01', '2026-08-27'


def load_names():
    p = ROOT / 'data' / 'stock_names.json'
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def tech_train(code, md):
    """2021~2024-12-31 深跌+放量信号 ≥10次 且 胜率≥65%（同 out_of_sample）"""
    px = md.price[code].dropna()
    px = px[px.index <= pd.Timestamp(TRAIN_DATE)]
    if len(px) < 60:
        return False, '数据短', 0
    ret20 = px / px.shift(20) - 1
    signals = ret20[ret20 < -0.20]
    if code in md.volume.columns:
        vol = md.volume[code].dropna()
        vr = vol / vol.shift(1).rolling(20).mean()
        vv = vr.reindex(signals.index)
        signals = signals[vv > 0.7] if vv.notna().any() else signals
    if len(signals) < 5:
        return False, f'信号{len(signals)}次', 0
    px10 = px.shift(-10)
    fwd = px10.reindex(signals.index).dropna()
    sig_px = px.reindex(fwd.index)
    wins = (fwd > sig_px).sum()
    wr = wins / len(fwd) if len(fwd) else 0
    ok = len(signals) >= 10 and wr >= 0.65
    return ok, f'信号{len(signals)}次/胜率{wr:.0%}', wr


def main():
    import argparse as _argparse
    import logging as _logging
    _ap = _argparse.ArgumentParser()
    _ap.add_argument("--train-only", action="store_true")
    _ap.add_argument("--ww-exit", type=int, default=None, help="王文五恶化退出阈值")
    _ap.add_argument("--ww-min", type=int, default=None, help="王文五进场门槛(项数>=此值才买)")
    _a = _ap.parse_args()
    _logging.disable(_logging.CRITICAL)
    from core.data_loader import load_data
    from core.backtest import BacktestPipeline
    from core.strategy import SimpleStrategy

    codes = [l.strip().zfill(6) for l in open(TICKER_FILE) if l.strip()]
    names = load_names()
    md = load_data(source='freestockdb', tickers=codes, start=START, end=END,
                   frequency='1d', fq='qfq')

    print("=" * 70)
    print(f"📋 300只随机池技术面筛选 | 判断基准日 {TRAIN_DATE}")
    print("=" * 70)
    rows = []
    for code in codes:
        ok, desc, wr = tech_train(code, md)
        rows.append({'code': code, 'ok': ok, 'desc': desc})
    df = pd.DataFrame(rows)
    passed = df[df['ok']]['code'].tolist()
    print(f"技术面合格: {len(passed)} / {len(codes)}")
    for c in passed:
        d = df[df['code'] == c]['desc'].iloc[0]
        print(f"  {c} {names.get(c,'?'):6s} [{d}]")

    if _a.train_only:
        print("\n（--train-only）")
        return

    def run_pool(tickers, tag, ww=None, wwmin=None):
        if not tickers:
            print(f"\n[{tag}] 空池，跳过"); return
        from core.data_loader import load_data as _ld
        sub = _ld(source='freestockdb', tickers=tickers, start=START, end=END,
                  frequency='1d', fq='qfq')
        st = SimpleStrategy(5, 20)
        eng = BacktestPipeline(st, top_n=10, risk_config={}, verbose=False,
                               stop_loss_pct=None, take_profit_pct=0.30,
                               trend_gate='multi', ww_exit=ww, ww_min=wwmin)
        eng.trend_gate_threshold = 2
        with contextlib.redirect_stdout(io.StringIO()):
            eng.run(sub, initial_cash=500000, auto_save=False, trade_start=TEST_START)
        eq = eng.equity_curve
        seg = eq[eq.index >= pd.Timestamp(TEST_START)]
        r = seg.iloc[-1] / seg.iloc[0] - 1 if len(seg) > 60 else float('nan')
        dd = (seg / seg.cummax() - 1).min() if len(seg) > 60 else float('nan')
        tr = eng.trades
        tr = tr[pd.to_datetime(tr['Date']) >= pd.Timestamp(TEST_START)] if not tr.empty else tr
        print(f"[{tag}] {len(tickers)}只 | 2025起收益 {r:+.1%} | 回撤 {dd:.1%} | "
              f"Sharpe {eng.sharpe:.2f} | 2025起交易{len(tr)}", flush=True)

    print("\n" + "=" * 70)
    print(f"实测期 {TEST_START}~{END}（样本外，multi门 无止损 止盈30%）")
    print("=" * 70)
    run_pool(passed, "技术面合格", ww=_a.ww_exit, wwmin=_a.ww_min)
    # 随机未筛出组（同数量对照）
    random.seed(99)
    not_passed = [c for c in codes if c not in passed]
    rand_ctrl = random.sample(not_passed, min(len(passed), len(not_passed)))
    run_pool(rand_ctrl, "随机对照(同数量)", ww=_a.ww_exit, wwmin=_a.ww_min)
    run_pool(codes, "全300对照", ww=_a.ww_exit, wwmin=_a.ww_min)


if __name__ == '__main__':
    main()
