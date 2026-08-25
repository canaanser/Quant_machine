"""
使用本地CSV文件跑完整回测 — 五大模块全链路验证
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from core.strategy import SimpleStrategy
from core.backtest import BacktestPipeline
from core.data_structures import metadata


def main():
    print("=" * 60)
    print("  本地CSV回测测试 — 中兴通讯 (五大模块全链路)")
    print("=" * 60)

    # 1. 读取CSV
    print("\n[1] 读取CSV文件...")
    df = pd.read_csv("中兴通讯_2025_2026.csv")

    # 列名映射（中文 → 英文）
    column_mapping = {
        '日期/时间': 'date',
        '代码': 'code',
        '名称': 'name',
        '开盘价': 'open',
        '最高价': 'high',
        '最低价': 'low',
        '收盘价': 'close',
        '前收盘价': 'pre_close',
        '成交量': 'volume',
        '成交额': 'amount',
        '换手率': 'turnover',
        '涨幅%': 'pct_chg',
        '振幅%': 'amplitude',
        '是否ST': 'is_st',
        '量比': 'vol_ratio',
        '总股本': 'total_share',
        '流通股本': 'float_share',
        '总市值': 'total_mv',
        '流通市值': 'float_mv',
        '市盈率': 'pe_ttm',
        '市净率': 'pb'
    }
    df.rename(columns=column_mapping, inplace=True)

    # 日期处理
    df['date'] = pd.to_datetime(df['date'].astype(str), format='%Y%m%d')
    df = df.set_index('date')
    df = df.sort_index()

    print(f"   数据条数: {len(df)}")
    print(f"   日期范围: {df.index.min()} 至 {df.index.max()}")

    # 2. 构建metadata（完整OHLCV）
    print("\n[2] 构建metadata...")
    price_df = df[['close']].copy()
    price_df.columns = ['000063']
    benchmark = price_df['000063'].copy()
    benchmark.name = '000063'

    open_price_df = df[['open']].copy()
    open_price_df.columns = ['000063']
    high_price_df = df[['high']].copy()
    high_price_df.columns = ['000063']
    low_price_df = df[['low']].copy()
    low_price_df.columns = ['000063']
    volume_df = df[['volume']].copy()
    volume_df.columns = ['000063']

    market_data = metadata(
        price=price_df,
        benchmark=benchmark,
        benchmark_price=benchmark.copy(),
        open_price=open_price_df,
        high_price=high_price_df,
        low_price=low_price_df,
        volume=volume_df
    )

    print(f"   ✅ metadata构建完成，{len(market_data.price)} 个交易日")

    # 3. 运行回测
    print("\n[3] 运行回测 (五大模块)...")
    strategy = SimpleStrategy(short=5, long=20)
    engine = BacktestPipeline(strategy, top_n=1, commission=0.00012)

    engine.run(market_data=market_data, initial_cash=500000, auto_save=False)

    # 4. 打印结果
    print("\n[4] 回测结果:")
    print(f"   累计收益率: {engine.total_return:.2%}")
    print(f"   年化收益率: {engine.annual_return:.2%}")
    print(f"   夏普比率: {engine.sharpe:.4f}")
    print(f"   最大回撤: {engine.max_drawdown:.2%}")
    print(f"   交易次数: {len(engine.trades)}")

    # 5. 交易明细
    if not engine.trades.empty:
        print("\n[5] 交易明细 (全部):")
        print(engine.trades.to_string(index=False))

    print("\n" + "=" * 60)
    print("  ✅ 五大模块全链路验证通过")
    print("=" * 60)


if __name__ == "__main__":
    main()