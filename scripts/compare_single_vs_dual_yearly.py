# -*- coding: utf-8 -*-
"""
单腿 vs 双腿：分年收益对比（验证 1234% 是不是单年暴击）
=====================================================================
2026-08-28 小二陈：DualLeg 84 只 10 年跑出 1234.60%（Simple 338.57%），
需验证收益构成——逐年拆分，看是否集中在某一年（如 2026 科技主升浪），
以及各年份双腿是否稳定优于单腿。

用法（Windows，需 stockdb.exe 服务）：
    cd E:/stockgate/Quant_Alpha_System
    python scripts/compare_single_vs_dual_yearly.py
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy, DualLegStrategy
import config.config as config_mod

START, END = '2017-01-01', '2026-08-27'
INITIAL_CASH = 500000
DEFAULT_TICKERS = list(config_mod.SCAN_TICKERS)


def yearly_returns(engine) -> dict:
    """从 equity_curve 按自然年切分算收益"""
    eq = engine.equity_curve
    years = {}
    for year in sorted(set(eq.index.year)):
        seg = eq[eq.index.year == year]
        if len(seg) > 1:
            years[year] = seg.iloc[-1] / seg.iloc[0] - 1
    return years


def main():
    import argparse
    parser = argparse.ArgumentParser(description="单腿 vs 双腿 分年收益对比")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    print(f"🚀 数据加载：{len(tickers)} 只，{args.start} ~ {args.end} ...")
    t0 = time.time()
    market_data = load_data(
        source='freestockdb', tickers=tickers,
        start=args.start, end=args.end, frequency='1d', fq='qfq'
    )
    print(f"✅ 加载完成 {market_data.price.shape[0]} 交易日，耗时 {time.time()-t0:.1f}s")

    engines = {}
    for name, cls in (("Simple", SimpleStrategy), ("DualLeg", DualLegStrategy)):
        t0 = time.time()
        eng = BacktestPipeline(cls(5, 20), top_n=10, verbose=False)
        eng.run(market_data, initial_cash=INITIAL_CASH, auto_save=False)
        engines[name] = eng
        print(f"✅ {name} 回测完成：累计 {eng.total_return:.2%}，耗时 {time.time()-t0:.1f}s")

    y_simple = yearly_returns(engines["Simple"])
    y_dual = yearly_returns(engines["DualLeg"])

    all_years = sorted(set(y_simple) | set(y_dual))
    print("\n" + "=" * 52)
    print(f"{'年份':<8}{'Simple':>11}{'DualLeg':>11}{'差值':>10}")
    print("-" * 52)
    for y in all_years:
        s = y_simple.get(y, 0)
        d = y_dual.get(y, 0)
        mark = " ✅" if d > s else " ❌"
        print(f"{y:<8}{s:>10.2%}{d:>10.2%}{d-s:>9.2%}{mark}")
    print("-" * 52)
    s_total = engines["Simple"].total_return
    d_total = engines["DualLeg"].total_return
    print(f"{'累计':<8}{s_total:>10.2%}{d_total:>10.2%}{d_total-s_total:>9.2%}")
    print(f"{'年化':<8}{engines['Simple'].annual_return:>10.2%}{engines['DualLeg'].annual_return:>10.2%}")
    print(f"{'Sharpe':<8}{engines['Simple'].sharpe:>10.2f}{engines['DualLeg'].sharpe:>10.2f}")
    print(f"{'最大回撤':<8}{engines['Simple'].max_drawdown:>10.2%}{engines['DualLeg'].max_drawdown:>10.2%}")
    print(f"{'交易数':<8}{len(engines['Simple'].trades):>10d}{len(engines['DualLeg'].trades):>10d}")
    print("=" * 52)
    print("注：✅ 表示该年双腿跑赢单腿；若双腿优势集中在 1-2 年，需警惕单年暴击。")


if __name__ == "__main__":
    main()
