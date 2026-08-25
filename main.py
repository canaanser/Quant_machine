"""
命令行回测入口（双均线金叉 + freestockdb）
"""

import sys
import pandas as pd
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from core.data_loader import load_data
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy
from config import INITIAL_CASH
# ===== 调试开关（全局控制所有打印日志） =====
# True  = 打印所有调试日志（形态扫描、大盘因子、金叉死叉、风控审批）
# False = 静默运行（只显示数据加载、交易汇总、绩效报告）
DEBUG_MODE = False   # ← 改这里就行


def main():
    print("⚙️ 启动命令行回测（双均线金叉 + freestockdb）...")

    # 1. 加载数据（使用 freestockdb）
    market_data = load_data(
        source='freestockdb',
        tickers=['000063'],
        start='2025-01-02',
        end='2026-08-11'
    )

    print(f"✅ 数据加载成功: {len(market_data.price)} 个交易日, {len(market_data.price.columns)} 只股票")

    # 2. 初始化策略（verbose 跟随 DEBUG_MODE）
    strategy = SimpleStrategy(short=5, long=20, verbose=DEBUG_MODE)

    # 3. 初始化回测引擎（verbose 跟随 DEBUG_MODE）
    print(f"🔍 main.py 中 DEBUG_MODE 的值 = {DEBUG_MODE}")
    engine = BacktestPipeline(
        strategy=strategy,
        top_n=10,
        verbose=DEBUG_MODE
    )
    print(f"🔍 engine.verbose 的值 = {engine.verbose}")
    # 4. 运行回测（初始资金从 config 读取）
    engine.run(
        market_data=market_data,
        initial_cash=INITIAL_CASH
    )

    # 5. 打印绩效报告
    engine.print_report()


if __name__ == "__main__":
    main()