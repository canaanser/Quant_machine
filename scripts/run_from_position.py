# -*- coding: utf-8 -*-
"""
模式切换续跑脚本：从实盘当前持仓断点续跑（建仓档 → 进攻档）
=====================================================================
2026-08-28 小二陈（老板需求）：
  实盘两阶段打法：建仓期保守（低仓位/严风控）→ 有利润后切进攻（高仓位）。
  切换时系统必须"接住"当前实盘持仓——本脚本从持仓文件 + 断点日期开始，
  用新模式参数续跑，验证新模式在当前持仓上的表现。

用法（Windows，需 stockdb.exe 服务，python -B 防缓存）：
  1) 准备持仓文件 positions.json：
     {"000063": {"shares": 1000, "avg_cost": 35.50}, "600498": {"shares": 500, "avg_cost": 40.00}}
  2) 续跑：
     python -B scripts/run_from_position.py --position positions.json --start 2026-08-01 --mode 建仓
     python -B scripts/run_from_position.py --position positions.json --start 2026-08-01 --mode 进攻

输出：新模式下的净值/近期窗口/回撤/交易。
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import pandas as pd
from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy
from config.risk_config import DEFAULT_RISK_CONFIG
import config.config as config_mod

# ===== 模式参数表（建仓档 / 进攻档）=====
# 建仓档：保本优先——轻仓/严止损/质量过滤全开
# 进攻档：收益优先——重仓/宽止损（有利润垫后切换）
MODE_CONFIG = {
    '建仓': {
        'risk': {'MAX_SINGLE_POSITION_RATIO': 0.10, 'BASE_POSITION_RATIO': 0.20},
        'strategy': {'quality_filter': True, 'quality_penalty': 0.1, 'bottom_confirm': True},
        'stop_loss_pct': 0.05,  # 铁律止损 5%（筑底确认保证买入质量，止损可行）
        'batch_exit': True, 'protect_days': 2,
        'desc': '轻仓10%/铁律止损5%/筑底确认/分批/保护期——实盘建仓保本',
    },
    '进攻': {
        'risk': {'MAX_SINGLE_POSITION_RATIO': 0.30, 'BASE_POSITION_RATIO': 0.50},
        'strategy': {'quality_filter': True, 'quality_penalty': 0.1, 'bottom_confirm': True},
        'stop_loss_pct': 0.08,  # 宽止损 8%（有利润垫）
        'batch_exit': True,
        'desc': '重仓30%/止损8%/筑底确认/分批——利润最大化',
    },
}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="实盘介入模拟（零持仓/断点续跑）")
    parser.add_argument("--position", default=None, help="持仓 JSON 文件（零持仓省略或空文件 {}）")
    parser.add_argument("--tickers", default="", help="候选池（与持仓分离，零持仓建仓时用此选池）")
    parser.add_argument("--start", required=True, help="介入起始日期（如 2025-01-01）")
    parser.add_argument("--mode", choices=list(MODE_CONFIG.keys()), default='建仓')
    parser.add_argument("--end", default='2026-08-27', help="结束日期（默认数据最新 2026-08-27）")
    parser.add_argument("--total", type=float, default=500000, help="总资金（默认50万）")
    parser.add_argument("--dc-low", type=float, default=-0.40, help="死叉低位阈值（默认-0.40，疑似底背离不卖）")
    parser.add_argument("--dc-strength", type=float, default=0.15, help="死叉强度阈值（默认0.15，弱死叉不卖）")
    parser.add_argument("--gc-high", type=float, default=-0.20, help="金叉高位阈值（默认-0.20，距250日高>-0.20拒买追高）")
    parser.add_argument("--print-trades", action="store_true",
                        help="打印每笔交易明细（含该笔完成后的总仓位=持仓市值/总资产）")
    args = parser.parse_args()

    positions = {}
    if args.position and Path(args.position).exists():
        positions = json.loads(Path(args.position).read_text(encoding='utf-8'))
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    else:
        tickers = list(positions.keys())
    if not tickers:
        print("❌ 无标的：请用 --tickers 指定候选池，或 --position 传持仓文件")
        return
    # 现金 = 总资金 - 持仓成本（2026-08-28 修复：此前现金没扣持仓成本，总资产虚高）
    pos_cost = sum(p['shares'] * p.get('avg_cost', 0) for p in positions.values())
    cash = args.total - pos_cost
    print(f"📦 初始持仓 {len(positions)} 只: {[(c, p['shares'], p.get('avg_cost')) for c, p in positions.items()]}")
    print(f"💰 总资金 {args.total:,.0f} - 持仓成本 {pos_cost:,.0f} = 现金 {cash:,.0f}")
    print(f"🎯 候选池 {len(tickers)} 只，{args.start} 起 {'零持仓实盘介入' if not positions else '断点续跑'}")

    cfg = MODE_CONFIG[args.mode]
    print(f"🎯 模式「{args.mode}」: {cfg['desc']}")
    print(f"   风控: {cfg['risk']}")

    # 数据从断点前拉（warmup 历史），引擎 trade_start 前不交易
    load_start = str(pd.Timestamp(args.start) - pd.DateOffset(years=2))[:10]
    print(f"🚀 加载数据（断点前 2 年 warmup）: {load_start} ~ {args.end} ...")
    md = load_data(source='freestockdb', tickers=tickers,
                   start=load_start, end=args.end, frequency='1d', fq='qfq')
    print(f"✅ 加载完成 {md.price.shape[0]} 交易日")

    # 风险配置：模式参数覆盖默认
    rc = dict(DEFAULT_RISK_CONFIG)
    rc.update(cfg['risk'])
    strategy = SimpleStrategy(5, 20, **cfg['strategy'])
    engine = BacktestPipeline(strategy, top_n=10, risk_config=rc, verbose=False,
                              stop_loss_pct=cfg.get('stop_loss_pct'),
                              batch_exit=cfg.get('batch_exit', False),
                              protect_days=cfg.get('protect_days', 0))
    # 死叉真假判定参数（2026-08-29 实验）：--dc-low/--dc-strength
    engine.risk_manager.deadcross_low = args.dc_low
    engine.risk_manager.deadcross_strength = args.dc_strength
    engine.risk_manager.goldencross_high = args.gc_high
    print(f"🔍 死叉判定参数: 低位 {args.dc_low} / 强度 {args.dc_strength}")
    engine.run(md, initial_cash=cash, auto_save=False, trade_start=args.start,
               initial_positions={c: {"name": c, "shares": p['shares'], "avg_cost": p.get('avg_cost', 0)} for c, p in positions.items()})

    print("\n" + "=" * 60)
    # 死叉驳回统计（诊断：浮盈/底背离/低位各驳回多少次，真死叉放行几次）
    try:
        st = engine.risk_manager.deadcross_stats
        print(f"🔍 死叉判定统计: 浮盈驳回{st['浮盈']} 底背离驳回{st['底背离']} "
              f"低位驳回{st['低位']} 真死叉放行{st['真死叉']}")
    except Exception:
        pass
    print(f"模式「{args.mode}」续跑结果（{args.start} ~ {args.end}）")
    print("=" * 60)
    print(f"累计收益:   {engine.total_return:>10.2%}")
    print(f"年化收益:   {engine.annual_return:>10.2%}")
    print(f"Sharpe:     {engine.sharpe:>10.2f}")
    print(f"最大回撤:   {engine.max_drawdown:>10.2%}")
    print(f"交易数:     {len(engine.trades):>10d}")
    # 期末持仓
    print(f"\n期末持仓:")
    for sym, p in engine.adapter.positions.items():
        print(f"  {sym}: {p['shares']}股 @ {p['avg_cost']:.2f}")
    print(f"期末现金: {engine.adapter.cash:,.0f}")
    print("=" * 60)

    # 每笔交易明细（含该笔完成后的总仓位，2026-08-29 老板要求，无歧义）
    if args.print_trades:
        print("\n📊 每笔交易明细（总仓位 = 该笔成交后持仓市值/总资产）")
        print(f"{'日期':<12}{'代码':<8}{'操作':<6}{'价格':>9}{'数量':>8}{'总仓位':>9}")
        print("-" * 55)
        for _, r in engine.trades.iterrows():
            tp = float(r.get('total_position', 0) or 0)
            print(f"{str(r.get('Date', ''))[:10]:<12}{r.get('Stock', ''):<8}"
                  f"{str(r.get('Action', '')):<6}{float(r.get('Price', 0)):>9.2f}"
                  f"{int(r.get('Shares', 0)):>8}{tp:>8.1%}")
        print("=" * 60)


if __name__ == "__main__":
    main()
