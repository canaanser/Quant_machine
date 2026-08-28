# -*- coding: utf-8 -*-
"""
死叉真假判定参数扫描（方案2 实验，2026-08-29 小二陈）
扫描 deadcross_low（低位阈值）× deadcross_strength（强度阈值）网格，
在精选15只实盘介入模拟（2025-01-01 建仓）上对比 累计/Sharpe/回撤/交易数。
用法（Windows，python -B）：
    python -B scripts/scan_deadcross_params.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / 'pybao') not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / 'pybao'))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import itertools
from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy
from config.config import SCAN_TICKERS_CURATED

CURATED = ','.join(SCAN_TICKERS_CURATED)


def run_once(deadcross_low, deadcross_strength, mode='建仓'):
    """跑一次实盘介入模拟（2025-01-01 起），返回指标 dict"""
    cfg = {
        '建仓': dict(stop_loss=0.05, batch=True, protect=2),
        '进攻': dict(stop_loss=0.08, batch=True, protect=0),
    }[mode]
    md = load_data(source='freestockdb', tickers=list(SCAN_TICKERS_CURATED),
                   start='2023-01-01', end='2026-08-27', frequency='1d', fq='qfq')
    from config.risk_config import DEFAULT_RISK_CONFIG
    import copy
    rc = copy.deepcopy(DEFAULT_RISK_CONFIG)
    rc.update({'MAX_SINGLE_POSITION_RATIO': 0.10 if mode == '建仓' else 0.30,
               'BASE_POSITION_RATIO': 0.20 if mode == '建仓' else 0.50})
    strategy = SimpleStrategy(5, 20, quality_filter=True, quality_penalty=0.1, bottom_confirm=True)
    engine = BacktestPipeline(strategy, top_n=10, risk_config=rc, verbose=False,
                              stop_loss_pct=cfg['stop_loss'], batch_exit=cfg['batch'],
                              protect_days=cfg['protect'])
    # 注入扫描参数
    engine.risk_manager.deadcross_low = deadcross_low
    engine.risk_manager.deadcross_strength = deadcross_strength
    engine.run(md, initial_cash=500000, auto_save=False, trade_start='2025-01-01')
    return {
        '累计': f"{engine.total_return:.2%}", 'Sharpe': f"{engine.sharpe:.2f}",
        '回撤': f"{engine.max_drawdown:.2%}", '交易': len(engine.trades),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="死叉真假判定参数扫描")
    parser.add_argument("--mode", default='建仓', choices=['建仓', '进攻'])
    args = parser.parse_args()

    lows = [-0.30, -0.40, -0.50]
    strengths = [0.10, 0.15, 0.20]
    print(f"🔍 死叉判定参数扫描（{args.mode}，精选15只，2025-01-01 实盘介入模拟）")
    print(f"   网格：低位阈值 {lows} × 强度阈值 {strengths}")
    print(f"   基准（改动前 {args.mode}）：建仓 92.99%/0.76/-25.93%/1966笔 | 进攻 158.91%/0.88/-34.31%/1549笔")
    print("=" * 70)
    print(f"{'低位':>6} {'强度':>6} {'累计':>9} {'Sharpe':>7} {'回撤':>8} {'交易':>6}")
    print("-" * 70)
    for low, st in itertools.product(lows, strengths):
        try:
            r = run_once(low, st, args.mode)
            print(f"{low:>6.2f} {st:>6.2f} {r['累计']:>9} {r['Sharpe']:>7} {r['回撤']:>8} {r['交易']:>6}")
        except Exception as e:
            print(f"{low:>6.2f} {st:>6.2f}   ❌ {str(e)[:50]}")


if __name__ == "__main__":
    main()
