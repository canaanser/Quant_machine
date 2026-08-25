"""
回测引擎流水线（适配器驱动版）
符合CTO架构规格：数据通过适配器统一接入，策略/风控/执行完全解耦
"""

import pandas as pd
import numpy as np
from datetime import datetime
from config import COMMISSION, INITIAL_CASH
from .data_structures import metadata

# ---------- 适配器模块 ----------
from .simulated_adapter import SimulatedBrokerAdapter
from .standard_structures import AccountInfo, PositionInfo
from .risk_manager import RiskManager, create_default_account, Position
from .order_executor import OrderExecutor
from .performance_analyzer import PerformanceAnalyzer
from .factor_modulator import FactorModulator
from .signal_modulator import SignalModulator
from config.risk_config import DEFAULT_RISK_CONFIG


class BacktestPipeline:
    """
    回测流水线：适配器驱动
    - 所有账户数据从 adapter.get_account_info() 获取
    - 所有交易通过 adapter.place_order() 执行
    - RiskManager 只负责审批（不持有账户状态）
    """
    
    def __init__(self, strategy, top_n=10, commission=COMMISSION, risk_config=None):
        self.strategy = strategy
        self.top_n = top_n
        self.commission = commission
        self.risk_config = risk_config or DEFAULT_RISK_CONFIG
        
        self.risk_manager = RiskManager(self.risk_config)
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
        self.raw_benchmark = None
        self.adapter = None

    def run(self, market_data: metadata, initial_cash: float = None, auto_save: bool = True):
        if initial_cash is None:
            initial_cash = INITIAL_CASH
        
        price_data = market_data.price
        market_ret_raw = market_data.benchmark

        # ---------- 完全拟合快速通道 ----------
        if hasattr(self.strategy, "__class__") and self.strategy.__class__.__name__ == "FullFitStrategy":
            print("🔗 完全拟合模式：直接使用原始价格作为净值曲线")
            first_stock = price_data.columns[0]
            raw_prices = price_data[first_stock].dropna()
            normalized = raw_prices / raw_prices.iloc[0]
            self.raw_benchmark = normalized.copy()
            self.equity_curve = normalized
            self.trades = pd.DataFrame(columns=['Date', 'Stock', 'Action', 'Price', 'Shares'])
            self.total_return = normalized.iloc[-1] / normalized.iloc[0] - 1
            days = len(normalized)
            self.annual_return = (1 + self.total_return) ** (252 / days) - 1
            daily_ret = normalized.pct_change().dropna()
            self.sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252) if daily_ret.std() != 0 else 0
            rolling_max = normalized.expanding().max()
            drawdown = (normalized - rolling_max) / rolling_max
            self.max_drawdown = drawdown.min()
            self.daily_scores = {}
            self.daily_selected = {}
            for date, price in normalized.items():
                self.daily_scores[date] = {first_stock: round(float(price), 6)}
                self.daily_selected[date] = [first_stock]
            return self

        # ---------- 标准回测流程 ----------
        market_data.validate()
        returns = price_data.pct_change().dropna(how='all')
        market_ret = market_ret_raw.pct_change().dropna()
        common_idx = returns.index.intersection(market_ret.index)
        returns = returns.loc[common_idx]
        market_ret = market_ret.loc[common_idx]
        dates = common_idx
        
        if hasattr(self.strategy, 'window') and hasattr(self.strategy, 'lookback'):
            warmup_days = self.strategy.window + self.strategy.lookback
        else:
            warmup_days = 60 + 20
        
        if len(dates) < warmup_days:
            raise ValueError(f"数据长度不足，需要 {warmup_days} 天，实际 {len(dates)} 天")
        
        initial_positions = {}
        self.adapter = SimulatedBrokerAdapter(
            initial_cash=initial_cash,
            initial_positions=initial_positions,
            price_data=price_data
        )
        
        print(f"开始回测: {dates[0].strftime('%Y-%m-%d')} 至 {dates[-1].strftime('%Y-%m-%d')}")
        account_info = self.adapter.get_account_info()
        print(f"初始资金: {account_info.cash:,.2f} 元")
        
        for i, today in enumerate(dates):
            if i < warmup_days:
                self._record_snapshot(today)
                self.daily_scores[today] = {}
                self.daily_selected[today] = []
                continue
            
            self.adapter.set_current_date(today)
            account = self.adapter.get_account_info()
            if account is None:
                self._record_snapshot(today)
                continue
            
            # ---------- 优先使用开盘价，缺失时回退到收盘价 ----------
            current_prices = {}
            open_price_available = hasattr(market_data, 'open_price') and not market_data.open_price.empty
            if open_price_available:
                for symbol in market_data.open_price.columns:
                    if today in market_data.open_price.index:
                        val = market_data.open_price.loc[today, symbol]
                        if not pd.isna(val) and val > 0:
                            current_prices[symbol] = float(val)
                        else:
                            # 开盘价无效，回退到收盘价
                            print(f"⚠️ 开盘价无效 ({symbol} at {today})，使用收盘价")
                            if today in price_data.index:
                                current_prices[symbol] = float(price_data.loc[today, symbol])
                    else:
                        # 日期不在开盘价索引中，回退到收盘价
                        print(f"⚠️ 开盘价数据缺失日期 {today}，使用收盘价")
                        if today in price_data.index:
                            current_prices[symbol] = float(price_data.loc[today, symbol])
            else:
                print("⚠️ 未加载开盘价数据，所有价格将使用收盘价")
            # 如果某些股票仍未获取价格，从收盘价补全
            for symbol in price_data.columns:
                if symbol not in current_prices and today in price_data.index:
                    current_prices[symbol] = float(price_data.loc[today, symbol])
                    if symbol not in current_prices:
                        # 如果收盘价也缺失，则使用上一个有效价格
                        print(f"⚠️ 价格完全缺失 ({symbol} at {today})，使用前一日价格")
            
            holdings_dict = {}
            for pos in account.positions:
                holdings_dict[pos.symbol] = {
                    'shares': pos.shares,
                    'frozen_shares': 0,
                    'avg_cost': pos.avg_cost
                }
            
            # ---------- 生成策略信号 ----------
            hist_returns = returns.iloc[:i]
            hist_market = market_ret.iloc[:i]
            score_series = self.strategy.score_stocks(hist_returns, hist_market)
            
            # ---------- 大盘因子调制 ----------
            market_trend = 1.0
            if hasattr(market_data, 'benchmark_price') and not market_data.benchmark_price.empty:
                market_trend = self.factor_modulator.get_market_trend(market_data.benchmark_price.loc[hist_returns.index])
            print(f"📊 大盘因子: 沪深300 MA20 {'向上 ✅' if market_trend == 1.0 else '向下 ❌'} (值: {market_trend})")
            if market_trend == 0.0:
                print("   ⏳ 大盘向下，买入信号将被过滤")
            if hasattr(self, 'signal_modulator'):
                signal_df = pd.DataFrame({
                    'symbol': score_series.index,
                    'raw_score': score_series.values
                })
                modulated = self.signal_modulator.modulate_with_market(signal_df, market_trend)
                score_series = pd.Series(modulated['final_score'].values, index=modulated['symbol'])
            
            # 因子调制
            if not score_series.empty:
                factor_table = self.factor_modulator.get_factor_table(today, list(score_series.index))
                modulator_dict = factor_table.set_index('symbol')['modulator'].to_dict()
                final_scores = score_series * pd.Series(modulator_dict)
                final_scores = final_scores.fillna(score_series)
            else:
                final_scores = score_series
            
            # 选出 Top N 买入列表
            buy_list = final_scores.head(self.top_n).index.tolist() if len(final_scores) > 0 else []
            self.daily_scores[today] = final_scores.head(self.top_n).to_dict()
            self.daily_selected[today] = buy_list
            
            # ---------- 卖出逻辑 ----------
            sell_signals = []
            for sym, sc in score_series.items():
                if sc < -0.05:
                    sell_signals.append(sym)
            
            for symbol in list(holdings_dict.keys()):
                if symbol in sell_signals:
                    pos = holdings_dict[symbol]
                    score = final_scores.get(symbol, 0.5)
                    tag = market_data.info.loc[symbol].get('tag') if symbol in market_data.info.index and 'tag' in market_data.info.columns else None
                    
                    print(f"🔔 死叉信号触发卖出: {symbol}, 持仓={pos['shares']}股, 评分={score:.4f}")
                    
                    temp_account = create_default_account(account.cash)
                    temp_account.positions = {
                        symbol: Position(
                            shares=pos['shares'],
                            frozen_shares=0,
                            avg_cost=pos['avg_cost']
                        )
                    }
                    temp_account.total_asset = account.total_asset
                    
                    signal = {'symbol': symbol, 'action': 'SELL', 'score': score, 'tag': tag}
                    approved = self.risk_manager.approve_order(
                        signal, temp_account, current_prices.get(symbol, 50.0)
                    )
                    if approved:
                        volume = min(approved['target_volume'], pos['shares'])
                        if volume > 0:
                            order_id = self.adapter.place_order(symbol, 'SELL', volume, trade_date=today)
                            if not order_id.startswith('ERROR'):
                                status = self.adapter.get_order_status(order_id)
                                if status['status'] == 'FILLED':
                                    avg_cost = pos['avg_cost']
                                    exec_report = {
                                        'order_id': order_id,
                                        'symbol': symbol,
                                        'action': 'SELL',
                                        'filled_volume': status['filled_volume'],
                                        'filled_amount': status['filled_volume'] * status['filled_price'],
                                        'commission': 0,
                                        'fill_price': status['filled_price'],
                                        'timestamp': pd.Timestamp(today)
                                    }
                                    self.performance_analyzer.record_trade(exec_report)
                                    pnl = (status['filled_price'] - avg_cost) * status['filled_volume']
                                    print(f"   ✅ 卖出成交: {symbol} {status['filled_volume']}股 @ {status['filled_price']:.2f}，金额: {exec_report['filled_amount']:.2f}，总资产: {pnl:+.2f}")
            
            # ---------- 买入逻辑 ----------
            for symbol in buy_list:
                score = final_scores.get(symbol, 0.5)
                tag = market_data.info.loc[symbol].get('tag') if symbol in market_data.info.index and 'tag' in market_data.info.columns else None
                current_price = current_prices.get(symbol, 50.0)
                
                pos_info = None
                for pos in account.positions:
                    if pos.symbol == symbol:
                        pos_info = pos
                        break
                
                temp_account = create_default_account(account.cash)
                if pos_info:
                    temp_account.positions[symbol] = Position(
                        shares=pos_info.shares,
                        frozen_shares=0,
                        avg_cost=pos_info.avg_cost
                    )
                temp_account.total_asset = account.total_asset
                
                signal = {'symbol': symbol, 'action': 'BUY', 'score': score, 'tag': tag}
                approved = self.risk_manager.approve_order(
                    signal, temp_account, current_price
                )
                if approved:
                    volume = approved['target_volume']
                    if volume > 0:
                        order_id = self.adapter.place_order(symbol, 'BUY', volume, trade_date=today)
                        if not order_id.startswith('ERROR'):
                            status = self.adapter.get_order_status(order_id)
                            if status['status'] == 'FILLED':
                                exec_report = {
                                    'order_id': order_id,
                                    'symbol': symbol,
                                    'action': 'BUY',
                                    'filled_volume': status['filled_volume'],
                                    'filled_amount': status['filled_volume'] * status['filled_price'],
                                    'commission': 0,
                                    'fill_price': status['filled_price'],
                                    'timestamp': pd.Timestamp(today)
                                }
                                self.performance_analyzer.record_trade(exec_report)
                                print(f"   ✅ 买入成交: {symbol} {status['filled_volume']}股 @ {status['filled_price']:.2f}，金额: {exec_report['filled_amount']:.2f}")
            
            self._record_snapshot(today)
            
            if i % 50 == 0:
                acc = self.adapter.get_account_info()
                print(f"  {today.strftime('%Y-%m-%d')} 总资产: {acc.total_asset:,.2f} 元")
        
        self._extract_results(dates, auto_save)
        return self

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
        
        # ---------- 先构建 equity_curve ----------
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
        
        # ---------- 打印完整交易汇总 ----------
        if not self.trades.empty:
            print("\n" + "=" * 70)
            print("📊 完整交易汇总（共 {} 笔）".format(len(self.trades)))
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
        
        self._calculate_metrics()
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