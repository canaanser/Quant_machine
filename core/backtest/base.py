# -*- coding: utf-8 -*-
"""
回测流水线基类（2026-08-26 小二陈：core/backtest.py 拆分为包）
职责：初始化、快照记录、结果提取、绩效指标、绘图、报告。
"""

import pandas as pd
import numpy as np

from config import COMMISSION, INITIAL_CASH
from ..risk_manager import RiskManager
from ..order_executor import OrderExecutor
from ..performance_analyzer import PerformanceAnalyzer
from ..factor_modulator import FactorModulator
from ..signal_modulator import SignalModulator
from config.risk_config import DEFAULT_RISK_CONFIG


class _BacktestBase:
    """回测流水线基类：初始化与结果处理（run 主循环在子类）"""

    def __init__(self, strategy, top_n=10, commission=COMMISSION, risk_config=None, verbose: bool = False):
        self.strategy = strategy
        self.top_n = top_n
        self.commission = commission
        self.risk_config = risk_config or DEFAULT_RISK_CONFIG
        self.verbose = verbose
        self.risk_manager = RiskManager(self.risk_config, verbose=self.verbose)
        self.order_executor = OrderExecutor()
        self.performance_analyzer = PerformanceAnalyzer()
        self.factor_modulator = FactorModulator()
        self.signal_modulator = SignalModulator()

        self.equity_curve = None
        self.trades = None
        self.total_return = 0
        self.annual_return = 0
        self.sharpe = 0
        self.max_drawdown = 0
        self.daily_scores = {}
        self.daily_selected = {}
        self.daily_early_scores = {}
        self.raw_benchmark = None
        self.adapter = None
    def _record_snapshot(self, date):
        if self.adapter is None:
            return
        account = self.adapter.get_account_info()
        if account:
            self.performance_analyzer.record_daily_snapshot(account, date, {})
    def _extract_results(self, dates, auto_save: bool = True):
        trades_list = []
        if hasattr(self.adapter, 'pending_orders'):
            for order_id, order in self.adapter.pending_orders.items():
                if order.get('status') == 'FILLED':
                    trades_list.append({
                        'Date': pd.Timestamp(order.get('submitted_at', dates[0])),
                        'Stock': order.get('symbol', ''),
                        'Action': order.get('action', ''),
                        'Price': order.get('price', 0),
                        'Shares': order.get('volume', 0)
                    })
        self.trades = pd.DataFrame(trades_list) if trades_list else pd.DataFrame(columns=['Date', 'Stock', 'Action', 'Price', 'Shares'])

        snapshots = self.performance_analyzer.daily_snapshots
        if snapshots:
            equity_df = pd.DataFrame(snapshots)
            if 'date' in equity_df.columns:
                equity_df = equity_df.set_index('date')
                self.equity_curve = equity_df['total_asset'] if 'total_asset' in equity_df.columns else pd.Series([INITIAL_CASH] * len(dates), index=dates)
            else:
                self.equity_curve = pd.Series([INITIAL_CASH] * len(dates), index=dates)
        else:
            self.equity_curve = pd.Series([INITIAL_CASH] * len(dates), index=dates)

        if not self.trades.empty:
            print("\n" + "=" * 70)
            print("📊 完整交易汇总（共 {} 笔）".format(len(self.trades)))
            print(f"  策略：{self.strategy.__class__.__name__}")
            print("=" * 70)
            print(f"{'日期':<12} {'股票':<8} {'操作':<6} {'价格':>8} {'数量':>6} {'总资产':>14}")
            print("-" * 70)

            asset_map = self.equity_curve.to_dict() if self.equity_curve is not None else {}

            for idx, row in self.trades.iterrows():
                date_str = row['Date'].strftime('%Y-%m-%d') if hasattr(row['Date'], 'strftime') else str(row['Date'])[:10]
                asset = asset_map.get(row['Date'], 0.0)
                asset_str = f"{asset:,.2f}" if asset > 0 else ""
                print(f"{date_str:<12} {row['Stock']:<8} {row['Action']:<6} {row['Price']:>8.2f} {row['Shares']:>6} {asset_str:>14}")
            print("=" * 70)
            print("💡 提示：以上交易与前端 K 线图买卖点完全一致")
        else:
            print("📊 无交易记录")

          # 早盘评分预测：回测结束后的下一个交易日
        if hasattr(self, '_final_early_score') and self._final_early_score is not None:
            print(f"\n📊 回测结束后一天的早盘评分预测: {self._final_early_score:.4f}")

        self._calculate_metrics()
        self._calculate_final_early_score()
        if auto_save:
            self.performance_analyzer.save_reports("outputs/backtest_results/performance/")
    def _calculate_metrics(self):
        eq = self.equity_curve.dropna()
        if len(eq) < 2:
            return
        self.total_return = eq.iloc[-1] / eq.iloc[0] - 1
        days = len(eq)
        self.annual_return = (1 + self.total_return) ** (252 / days) - 1
        daily_ret = eq.pct_change().dropna()
        self.sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252) if daily_ret.std() != 0 else 0
        rolling_max = eq.expanding().max()
        drawdown = (eq - rolling_max) / rolling_max
        self.max_drawdown = drawdown.min()
    def plot_performance(self, return_fig=False):
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        eq = self.equity_curve.dropna()
        if len(eq) < 2:
            fig = go.Figure()
            fig.add_annotation(text="数据不足，无法绘制图表", x=0.5, y=0.5, showarrow=False)
            return fig if return_fig else fig.show()
        benchmark_curve = eq.rolling(20, min_periods=1).mean()
        rolling_max = eq.expanding().max()
        drawdown = (eq - rolling_max) / rolling_max
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                            subplot_titles=("资金曲线（元）", "回撤", "日收益率分布"),
                            row_heights=[0.5, 0.25, 0.25])
        fig.add_trace(go.Scatter(x=eq.index, y=eq, mode='lines', name='策略资金', line=dict(color='blue', width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=benchmark_curve.index, y=benchmark_curve, mode='lines', name='基准(MA20)', line=dict(color='gray', width=1.5, dash='dash')), row=1, col=1)
        fig.add_trace(go.Scatter(x=drawdown.index, y=drawdown, mode='lines', name='回撤', fill='tozeroy', line=dict(color='red', width=1), fillcolor='rgba(255,0,0,0.2)'), row=2, col=1)
        daily_ret = eq.pct_change().dropna()
        fig.add_trace(go.Histogram(x=daily_ret, nbinsx=30, name='日收益率', marker_color='green', opacity=0.7), row=3, col=1)
        fig.add_vline(x=0, line_width=1, line_dash="dash", line_color="black", row=3, col=1)
        fig.update_layout(height=800, showlegend=True, hovermode='x unified', template='plotly_white')
        fig.update_xaxes(title_text="日期", row=3, col=1)
        fig.update_yaxes(title_text="资金 (元)", row=1, col=1)
        fig.update_yaxes(title_text="回撤", row=2, col=1)
        fig.update_yaxes(title_text="频次", row=3, col=1)
        return fig if return_fig else fig.show()
    def get_trades_df(self):
        return self.trades
    def print_report(self):
        print("\n========== 回测绩效报告 ==========")
        print(f"累计收益率: {self.total_return:.2%}")
        print(f"年化收益率: {self.annual_return:.2%}")
        print(f"夏普比率: {self.sharpe:.4f}")
        print(f"最大回撤: {self.max_drawdown:.2%}")
        print(f"交易次数: {len(self.trades)}")
        print("==================================")
    def _calculate_final_early_score(self):
        """
        回测结束后，基于最后一天的均线数据，计算下一个交易日的早盘评分
        假设下一个交易日的开盘价 = 最后一天的收盘价
        """
        if not hasattr(self, '_last_ma5') or not self._last_ma5:
            # 没有存储最后一天的均线数据，无法预测
            self._final_early_score = 0.5
            self._final_early_scores = []
            return

        if not hasattr(self.strategy, 'calculate_early_score'):
            self._final_early_score = 0.5
            self._final_early_scores = []
            return

        early_scores_list = []
        for symbol, close_price in self._last_close.items():
            try:
                open_next_day = close_price  # 用最后一天收盘价作为下一个交易日的模拟开盘价
                early = self.strategy.calculate_early_score(
                    open_price=open_next_day,
                    close_prev=close_price,
                    ma5_prev=self._last_ma5.get(symbol, close_price),
                    ma20_prev=self._last_ma20.get(symbol, close_price)
                )
                early_scores_list.append((symbol, early))
            except Exception as e:
                # 静默跳过
                pass

        if early_scores_list:
            avg_score = np.mean([s[1] for s in early_scores_list])
            self._final_early_score = avg_score
            self._final_early_scores = early_scores_list
            print(f"\n📊 回测结束后一天的早盘评分预测: {avg_score:.4f}")
            for symbol, score in early_scores_list:
                print(f"   {symbol}: {score:.4f}")
        else:
            self._final_early_score = 0.5
            self._final_early_scores = []
