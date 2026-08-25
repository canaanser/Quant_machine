"""
绩效归因分析模块 (旁路)
适配 AccountInfo 的 positions 为 List[PositionInfo] 格式
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional


class PerformanceAnalyzer:
    """
    绩效归因分析器（旁路）
    不修改任何数据，只读取并生成报表
    """
    
    def __init__(self):
        self.trade_history: List[dict] = []
        self.daily_snapshots: List[dict] = []
    
    def record_trade(self, execution_report: dict):
        """记录一笔成交（来自执行层）"""
        self.trade_history.append(execution_report)
    
    def record_daily_snapshot(self, account, date, market_prices: dict = None):
        """
        记录每日账户快照
        account: AccountInfo 对象 (positions 为 List[PositionInfo])
        """
        # 计算持仓市值
        market_value = 0.0
        if hasattr(account, 'positions') and account.positions:
            for pos in account.positions:
                # pos 是 PositionInfo 对象，有 symbol, shares, current_price
                if hasattr(pos, 'current_price') and pos.current_price > 0:
                    market_value += pos.shares * pos.current_price
                elif market_prices and pos.symbol in market_prices:
                    market_value += pos.shares * market_prices[pos.symbol]
                else:
                    # 用平均成本估算
                    market_value += pos.shares * pos.avg_cost
        
        self.daily_snapshots.append({
            'date': date,
            'total_asset': getattr(account, 'total_asset', 0.0),
            'cash': getattr(account, 'cash', 0.0),
            'market_value': market_value,
            'frozen_cash': getattr(account, 'frozen_cash', 0.0),
        })
    
    def generate_report(self) -> Dict[str, pd.DataFrame]:
        """生成三张绩效报表"""
        stock_df = self._calc_stock_performance()
        tag_df = self._calc_tag_performance()
        nav_df = self._calc_nav_curve()
        return {'stock': stock_df, 'tag': tag_df, 'nav': nav_df}
    
    def _calc_stock_performance(self) -> pd.DataFrame:
        """计算单股战绩表"""
        if not self.trade_history:
            return pd.DataFrame(columns=[
                'symbol', 'trade_count', 'win_rate', 'avg_profit_pct',
                'total_pnl', 'holding_days_avg', 'annual_return'
            ])
        # 简化实现
        df = pd.DataFrame(self.trade_history)
        results = []
        for symbol, group in df.groupby('symbol'):
            trade_count = len(group)
            # 暂时用占位值
            results.append({
                'symbol': symbol,
                'trade_count': trade_count,
                'win_rate': 0.0,
                'avg_profit_pct': 0.0,
                'total_pnl': 0.0,
                'holding_days_avg': 0.0,
                'annual_return': 0.0
            })
        return pd.DataFrame(results)
    
    def _calc_tag_performance(self) -> pd.DataFrame:
        """计算板块战绩表"""
        return pd.DataFrame(columns=['tag', 'total_pnl', 'win_rate', 'total_commission', 'trade_count'])
    
    def _calc_nav_curve(self) -> pd.DataFrame:
        """计算净值曲线"""
        if not self.daily_snapshots:
            return pd.DataFrame(columns=[
                'date', 'total_asset', 'cash', 'market_value',
                'daily_return', 'cum_return', 'max_drawdown'
            ])
        df = pd.DataFrame(self.daily_snapshots)
        df = df.sort_values('date')
        df['daily_return'] = df['total_asset'].pct_change().fillna(0)
        initial_asset = df['total_asset'].iloc[0] if not df.empty else 1.0
        df['cum_return'] = df['total_asset'] / initial_asset - 1 if initial_asset != 0 else 0
        cummax = df['cum_return'].expanding().max()
        df['max_drawdown'] = df['cum_return'] - cummax
        return df
    
    def save_reports(self, output_dir: str = "outputs/backtest_results/performance/"):
        """保存三张报表到CSV"""
        import os
        os.makedirs(output_dir, exist_ok=True)
        reports = self.generate_report()
        for name, df in reports.items():
            if not df.empty:
                df.to_csv(os.path.join(output_dir, f"{name}.csv"), index=False)
                print(f"💾 已保存: {name}.csv")
