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

import pandas as pd

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
    parser.add_argument("--no-quality", action="store_true",
                        help="关闭质量评分过滤（回到原版 Simple）")
    parser.add_argument("--verbose", action="store_true", help="打印诊断日志（定位仓位/审批问题）")
    parser.add_argument("--pos-off", action="store_true",
                        help="关闭位置软加权（纯 v1：深跌+放量，不按价格位置调整）")
    parser.add_argument("--bottom", action="store_true",
                        help="筑底确认（低点抬高企稳才买）")
    parser.add_argument("--mode", choices=['建仓', '进攻'], default=None,
                        help="模式档位：建仓=轻仓10%+铁律止损5%+分批+保护期；进攻=30%+止损8%")
    parser.add_argument("--stop-loss", type=float, default=None,
                        help="止损比例（如0.10）；不传用模式默认（建仓5%/进攻8%/标准无）")
    parser.add_argument("--take-profit", type=float, default=None,
                        help="止盈比例（如0.40）；不传=2×止损")
    parser.add_argument("--ext", action="store_true",
                        help="合并扩池：84 主池 + 78 只行业扩展池（162 只）")
    parser.add_argument("--old-sell", action="store_true",
                        help="旧版直接卖（2026-08-30 实验A）：死叉 score<-0.05 直接卖，跳过封控层浮盈/底背离/低位驳回")
    args = parser.parse_args()

    if args.ext:
        tickers = list(config_mod.SCAN_TICKERS) + list(config_mod.SCAN_TICKERS_EXT)
        print(f"📦 合并池 {len(tickers)} 只（主池 {len(config_mod.SCAN_TICKERS)} + 扩展 {len(config_mod.SCAN_TICKERS_EXT)}）")
    else:
        tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]

    # 位置软加权（老板强调"越跌越买要看价格位置"）：默认开；--pos-off 关闭回纯 v1
    pos_kw = {"quality_pos_boost": -1.0, "quality_pos_trim": 1.0} if args.pos_off else {}
    if args.bottom:
        pos_kw["bottom_confirm"] = True
    strategy = SimpleStrategy(5, 20, quality_filter=not args.no_quality, quality_penalty=0.1, **pos_kw)

    t0 = time.time()
    print(f"🚀 数据加载：{len(tickers)} 只，{args.start} ~ {args.end} ...")
    market_data = load_data(
        source='freestockdb', tickers=tickers,
        start=args.start, end=args.end, frequency='1d', fq='qfq'
    )
    t_load = time.time() - t0
    print(f"✅ 数据加载完成：{market_data.price.shape[0]} 交易日，耗时 {t_load:.1f}s")

    t0 = time.time()
    # 2026-08-28 定型：质量评分 v1（深跌<-20%+放量>0.7，不满足降权×0.1）+ 位置软加权（默认开）
    # 模式档位（老板两阶段打法）：建仓=轻仓10%+铁律止损5%+分批+保护期；进攻=30%+止损8%
    from config.risk_config import DEFAULT_RISK_CONFIG
    import copy
    rc = copy.deepcopy(DEFAULT_RISK_CONFIG)
    stop_loss = take_profit = None
    batch = protect = False
    if args.mode == '建仓':
        rc.update({'MAX_SINGLE_POSITION_RATIO': 0.10, 'BASE_POSITION_RATIO': 0.20})
        stop_loss, batch, protect = 0.05, True, 2
    elif args.mode == '进攻':
        rc.update({'MAX_SINGLE_POSITION_RATIO': 0.30, 'BASE_POSITION_RATIO': 0.50})
        stop_loss, batch = 0.08, True
    print(f"🎯 模式: {args.mode or '标准'} 风控={rc.get('MAX_SINGLE_POSITION_RATIO')} 止损={stop_loss}")
    if args.stop_loss is not None:
        stop_loss = args.stop_loss  # 敏感性测试：显式止损覆盖模式默认
    engine = BacktestPipeline(strategy, top_n=10, risk_config=rc, verbose=args.verbose,
                              stop_loss_pct=stop_loss, take_profit_pct=args.take_profit,
                              batch_exit=batch, protect_days=protect,
                              old_sell=args.old_sell)
    if args.old_sell:
        print("🔧 旧版直接卖已启用（跳过封控层：浮盈/底背离/低位驳回）")
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
    # 近期窗口报告（2026-08-28 老板视角：实盘从今天买，看近期）
    print("\n===== 近期窗口（实盘相关）=====")
    eq = engine.equity_curve
    for years in (1, 2, 3, 5):
        w0 = eq.index[-1] - pd.DateOffset(years=years)
        seg = eq[eq.index >= w0]
        if len(seg) > 60:
            wr = seg.iloc[-1] / seg.iloc[0] - 1
            wdd = (seg / seg.cummax() - 1).min()
            print(f"  近{years}年: 收益 {wr:+.2%}   区间最大回撤 {wdd:.2%}")
    print("=" * 60)


if __name__ == "__main__":
    main()
