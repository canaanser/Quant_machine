# -*- coding: utf-8 -*-
"""
样本外实测（2026-09-02 老板：2024年底判断选票，2025年起实测，无前视）
=====================================================================
训练期（判断，站在 2024-12-31，只用当时可见数据）：
  ① 王文五：pubDate ≤ 2024-12-31 的最新财报（2024Q3，2024-10 披露）+ 当日 pe/pb
  ② 技术面：2021~2024 K线 深跌+放量信号数 ≥10 且 10日胜率 ≥65%（现成标准）
  ③ 交集票 = 王文五合格 ∩ 技术面合格
实测期（2025-01-01 ~ 2026-08-27）：交集票跑回测（引擎逐日无前视），
  对照组：全部合格池（任一关合格）也跑——看筛掉的是不是亏钱货

用法（Windows）：python -B scripts/out_of_sample.py
"""
import sys
import json
import io
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

TRAIN_DATE = '2024-12-31'   # 判断基准日（站在这天，只看这天前的数据）
TEST_START = '2025-01-01'   # 实测起点
TEST_END = '2026-08-27'
DATA_START = '2021-01-01'   # 训练期 K线起点（技术面信号用）

OUT = ROOT / 'outputs'


def load_names():
    p = ROOT / 'data' / 'stock_names.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def wangwen_train(code, sel):
    """站在 2024-12-31 判王文五：只取 pubDate≤2024-12-31 的最新财报"""
    ind = sel.latest_indicator(code, TRAIN_DATE) or {}
    pe, pb = sel.realtime_pe_pb(code, TRAIN_DATE)
    if pe is None or pb is None:
        return False, '无估值', 0
    r1 = 0 < pe < 30 and pb < 5
    ocf = ind.get('ocf_to_operating_profit') if ind else None
    r2 = ocf is not None and ocf > 0.5
    gm = ind.get('gross_profit_margin') if ind else None
    nm = ind.get('net_profit_margin') if ind else None
    r4 = gm is not None and gm > 20 and nm is not None and nm > 0
    ry = ind.get('inc_revenue_year_on_year') if ind else None
    ny = ind.get('inc_net_profit_year_on_year') if ind else None
    r5 = ry is not None and ry > 0 and ny is not None and ny > 0
    n = sum([r1, r2, r4, r5])
    return n >= 3, f'王文{n}项', n


def tech_train(code, md, volume=None):
    """技术面：2021~2024-12-31 深跌+放量信号（用 md.price 序列，>=10次且胜率>=65%）"""
    px = md.price[code].dropna()
    px = px[px.index <= pd.Timestamp(TRAIN_DATE)]
    if len(px) < 60:
        return False, '数据短', 0
    vol = md.volume[code].dropna() if volume is not None and code in volume.columns else None
    # 深跌：20日跌>20%；放量：量比>0.7（用当日/20日均量）
    ret20 = px / px.shift(20) - 1
    signals = ret20[ret20 < -0.20]
    if vol is not None:
        vr = vol / vol.shift(1).rolling(20).mean()
        vv = vr.reindex(signals.index)
        signals = signals[vv > 0.7] if vv.notna().any() else signals
    if len(signals) < 5:
        return False, f'信号{len(signals)}次', 0
    # 10日胜率：向量化（信号日价 vs 10日后价），不逐信号循环（2026-09-02 提速）
    px10 = px.shift(-10)  # 第 i 行的值 = i+10 日价格
    fwd = px10.reindex(signals.index).dropna()
    sig_px = px.reindex(fwd.index)  # 信号日的实际价格（不是跌幅值！2026-09-02 修复 bug）
    wins = (fwd > sig_px).sum()
    winrate = wins / len(fwd) if len(fwd) else 0
    ok = len(signals) >= 10 and winrate >= 0.65
    return ok, f'信号{len(signals)}次/胜率{winrate:.0%}', winrate


def main():
    import logging as _logging
    _logging.disable(_logging.CRITICAL)
    from core.data_loader import load_data
    from core.backtest import BacktestPipeline
    from core.strategy import SimpleStrategy
    from selection.wangwen import WangwenSelector
    import config.config as cfg

    import argparse as _argparse
    _ap = _argparse.ArgumentParser()
    _ap.add_argument("--train-only", action="store_true", help="只跑训练期筛选，跳过回测")
    _a = _ap.parse_args()
    codes = list(cfg.SCAN_TICKERS)
    names = load_names()
    md = load_data(source='freestockdb', tickers=codes, start=DATA_START,
                   end=TEST_END, frequency='1d', fq='qfq')
    sel = WangwenSelector()

    # ===== 训练期判定（站在 2024-12-31）=====
    print("=" * 70)
    print(f"📋 样本外实测  |  判断基准日 {TRAIN_DATE}（只看当日可见数据）")
    print("=" * 70)
    rows = []
    for code in codes:
        ww_ok, ww_desc, ww_n = wangwen_train(code, sel)
        tech_ok, tech_desc, _ = tech_train(code, md, md.volume)
        rows.append({'code': code, 'ww': ww_ok, 'tech': tech_ok,
                     'ww_desc': ww_desc, 'tech_desc': tech_desc})
    df = pd.DataFrame(rows)
    ww_pass = df[df['ww']]['code'].tolist()
    tech_pass = df[df['tech']]['code'].tolist()
    both = df[(df['ww']) & (df['tech'])]['code'].tolist()
    print(f"\n训练期结果（2024-12-31 视角）:")
    print(f"  王文五合格: {len(ww_pass)} 只")
    print(f"  技术面合格: {len(tech_pass)} 只")
    print(f"  双过交集:   {len(both)} 只 -> {both}")
    for _, r in df[df['ww'] & df['tech']].iterrows():
        print(f"    {r['code']} {names.get(r['code'], '?'):6s} [{r['ww_desc']} | {r['tech_desc']}]")

    # ===== 实测期（2025 起，样本外）=====
    def run_pool(tickers, tag):
        if not tickers:
            print(f"\n[{tag}] 空池，跳过")
            return
        # 按组切片 md：只保留该组股票（2026-09-02 修复：引擎不支持限定tickers，需裁数据）
        sub_cols = [c for c in tickers if c in md.price.columns]
        if not sub_cols:
            print(f"\n[{tag}] 组内无可用数据，跳过")
            return
        from core.data_loader import load_data as _ld
        sub_md = _ld(source='freestockdb', tickers=sub_cols, start=DATA_START,
                     end=TEST_END, frequency='1d', fq='qfq')
        st = SimpleStrategy(5, 20)
        eng = BacktestPipeline(st, top_n=10, risk_config={}, verbose=False,
                               stop_loss_pct=None, take_profit_pct=None,
                               trend_gate='multi')
        eng.trend_gate_threshold = 2
        with contextlib.redirect_stdout(io.StringIO()):
            eng.run(sub_md, initial_cash=500000, auto_save=False,
                    trade_start=TEST_START)  # 2026-09-02 修复：2025起空仓起步（样本外真考验）
        # 只看 2025 起的窗口（样本外）
        eq = eng.equity_curve
        seg = eq[eq.index >= pd.Timestamp(TEST_START)]
        r = seg.iloc[-1] / seg.iloc[0] - 1 if len(seg) > 60 else float('nan')
        dd = (seg / seg.cummax() - 1).min() if len(seg) > 60 else float('nan')
        # 2025 起的交易笔数（样本外真实交易）
        tr = eng.trades
        if not tr.empty:
            tr = tr.copy()
            tr['Date'] = pd.to_datetime(tr['Date'])
            tr = tr[tr['Date'] >= pd.Timestamp(TEST_START)]
        print(f"[{tag}] {len(sub_cols)}只 | 2025起收益 {r:+.1%} | 回撤 {dd:.1%} | "
              f"Sharpe {eng.sharpe:.2f} | 2025起交易{len(tr)}", flush=True)

    if _a.train_only:
        print("\n（--train-only：跳过实测回测）")
        return
    print("\n" + "=" * 70)
    print(f"实测期 {TEST_START} ~ {TEST_END}（样本外，multi门 无止损）")
    print("=" * 70)
    run_pool(both, "双过交集")
    run_pool(ww_pass, "王文五合格(含未过技术面)")
    run_pool(tech_pass, "技术面合格(含未过王文)")
    run_pool(codes, "全84只对照")


if __name__ == '__main__':
    main()
