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
        'strategy': {'quality_filter': True, 'quality_penalty': 0.1},
        'stop_loss_pct': 0.20,  # 建仓档：极端止损 -20%（只防黑天鹅，敏感止损对抄底策略有害）
        'desc': '轻仓10%上限/极端止损20%/质量过滤——攒安全垫',
    },
    '进攻': {
        'risk': {'MAX_SINGLE_POSITION_RATIO': 0.30, 'BASE_POSITION_RATIO': 0.50},
        'strategy': {'quality_filter': True, 'quality_penalty': 0.1},
        'stop_loss_pct': 0.15,  # 进攻档：宽止损 -15%（有利润垫）
        'desc': '重仓30%上限/宽止损15%/质量过滤——利润最大化',
    },
}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="模式切换续跑（实盘持仓断点）")
    parser.add_argument("--position", required=True, help="持仓 JSON 文件：{\"code\": {\"shares\": n, \"avg_cost\": p}}")
    parser.add_argument("--start", required=True, help="断点起始日期（如 2026-08-01）")
    parser.add_argument("--mode", choices=list(MODE_CONFIG.keys()), default='建仓')
    parser.add_argument("--end", default='2026-08-27', help="结束日期（默认数据最新 2026-08-27）")
    parser.add_argument("--total", type=float, default=500000, help="总资金（含持仓市值，默认50万）")
    args = parser.parse_args()

    pos_path = Path(args.position)
    if not pos_path.exists():
        print(f"❌ 持仓文件不存在: {pos_path}")
        return
    positions = json.loads(pos_path.read_text(encoding='utf-8'))
    tickers = list(positions.keys())
    # 现金 = 总资金 - 持仓成本（2026-08-28 修复：此前现金没扣持仓成本，总资产虚高）
    pos_cost = sum(p['shares'] * p.get('avg_cost', 0) for p in positions.values())
    cash = args.total - pos_cost
    print(f"📦 持仓 {len(positions)} 只: {[(c, p['shares'], p.get('avg_cost')) for c, p in positions.items()]}")
    print(f"💰 总资金 {args.total:,.0f} - 持仓成本 {pos_cost:,.0f} = 现金 {cash:,.0f}")

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
                              stop_loss_pct=cfg.get('stop_loss_pct'))
    engine.run(md, initial_cash=cash, auto_save=False, trade_start=args.start,
               initial_positions={c: {"name": c, "shares": p['shares'], "avg_cost": p.get('avg_cost', 0)} for c, p in positions.items()})

    print("\n" + "=" * 60)
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


if __name__ == "__main__":
    main()
