# -*- coding: utf-8 -*-
"""
双均线金叉（SimpleStrategy）组合回测入口
========================================
2026-08-28 小二陈：
  - TrendStrengthStrategy 已删除（组合层面落败），SimpleStrategy 为唯一主力传统策略。
  - 评分已向量化预计算（prepare 查表，129x 提速）：84 只 10 年由 ~100 分钟降至分钟级。
  - 本脚本供 Windows 端复跑验证速度与指标。

用法（Windows，需 stockdb.exe 服务运行）：
    cd E:/stockgate/Quant_Alpha_System
    python scripts/run_simple_pool.py                        # 84 只主池 2017~今
    python scripts/run_simple_pool.py --tickers 000063 --start 2025-01-01 --end 2026-07-31
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy
import config.config as config_mod

START, END = '2017-01-01', '2026-08-27'
INITIAL_CASH = 500000
DEFAULT_TICKERS = list(config_mod.SCAN_TICKERS)  # 84 只主池


def main():
    import argparse
    parser = argparse.ArgumentParser(description="双均线金叉（SimpleStrategy）组合回测")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS),
                        help="股票代码，逗号分隔（默认 84 只主池）")
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]

    t0 = time.time()
    print(f"🚀 数据加载：{len(tickers)} 只，{args.start} ~ {args.end} ...")
    market_data = load_data(
        source='freestockdb', tickers=tickers,
        start=args.start, end=args.end, frequency='1d', fq='qfq'
    )
    t_load = time.time() - t0
    print(f"✅ 数据加载完成：{market_data.price.shape[0]} 交易日，耗时 {t_load:.1f}s")

    t0 = time.time()
    engine = BacktestPipeline(SimpleStrategy(short=5, long=20, verbose=False), top_n=10, verbose=False)
    engine.run(market_data, initial_cash=INITIAL_CASH, auto_save=False)
    t_run = time.time() - t0

    print("\n" + "=" * 60)
    print("双均线金叉（SimpleStrategy 5/20）组合结果")
    print("=" * 60)
    print(f"累计收益:   {engine.total_return:>10.2%}")
    print(f"年化收益:   {engine.annual_return:>10.2%}")
    print(f"Sharpe:     {engine.sharpe:>10.2f}")
    print(f"最大回撤:   {engine.max_drawdown:>10.2%}")
    print(f"交易数:     {len(engine.trades):>10d}")
    print(f"耗时:       加载 {t_load:.1f}s + 回测 {t_run:.1f}s = {t_load + t_run:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
