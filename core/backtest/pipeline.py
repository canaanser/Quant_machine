# -*- coding: utf-8 -*-
"""
回测流水线主类（2026-08-26 小二陈：core/backtest.py 拆分为包）
组合：_BacktestBase（初始化/结果/指标）+ _PatternScanMixin（形态/权重）
      + _ExecutionMixin（评分/买卖执行）。
run() 主循环骨架：段落逻辑已下沉到各 Mixin 的私有方法。
"""

import logging

import pandas as pd
import numpy as np

from config import COMMISSION, INITIAL_CASH
from core.logger import get_logger
from ..data_structures import metadata
from ..simulated_adapter import SimulatedBrokerAdapter
from .base import _BacktestBase
from .pattern_mixin import _PatternScanMixin
from .execution_mixin import _ExecutionMixin

logger = get_logger(__name__)


class BacktestPipeline(_BacktestBase, _PatternScanMixin, _ExecutionMixin):
    """
    回测流水线：适配器驱动
    - 所有账户数据从 adapter.get_account_info() 获取
    - 所有交易通过 adapter.place_order() 执行
    - RiskManager 只负责审批（不持有账户状态）
    """

    def __init__(self, strategy, top_n=10, commission=COMMISSION, risk_config=None, verbose: bool = False):
        super().__init__(strategy, top_n=top_n, commission=commission,
                         risk_config=risk_config, verbose=verbose)
        # verbose=True 时，本包 logger 提升到 DEBUG 级（调试细节可见，保持原有行为）
        if verbose:
            logging.getLogger("core.backtest").setLevel(logging.DEBUG)

    def run(self, market_data: metadata, initial_cash: float = None, auto_save: bool = True):
        if initial_cash is None:
            initial_cash = INITIAL_CASH

        price_data = market_data.price
        market_ret_raw = market_data.benchmark

        if hasattr(self.strategy, "__class__") and self.strategy.__class__.__name__ == "FullFitStrategy":
            logger.info("🔗 完全拟合模式：直接使用原始价格作为净值曲线")
            first_stock = price_data.columns[0]
            raw_prices = price_data[first_stock].dropna()
            normalized = raw_prices / raw_prices.iloc[0]
            self.raw_benchmark = normalized.copy()
            self.equity_curve = normalized
            self.trades = pd.DataFrame(columns=['Date', 'Stock', 'Action', 'Price', 'Shares'])
            self.total_return = normalized.iloc[-1] / normalized.iloc[0] - 1
            days = len(normalized)
            self.annual_return = (1 + self.total_return) ** (252 / days) - 1
            daily_ret = normalized.pct_change(fill_method=None).dropna()
            self.sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252) if daily_ret.std() != 0 else 0
            rolling_max = normalized.expanding().max()
            drawdown = (normalized - rolling_max) / rolling_max
            self.max_drawdown = drawdown.min()
            self.daily_scores = {}
            self.daily_selected = {}
            self.daily_early_scores = {}
            for date, price in normalized.items():
                self.daily_scores[date] = {first_stock: round(float(price), 6)}
                self.daily_selected[date] = [first_stock]
                self.daily_early_scores[date] = 0.5
            return self

        market_data.validate()
        returns = price_data.pct_change(fill_method=None).dropna(how='all')
        market_ret = market_ret_raw.pct_change(fill_method=None).dropna()
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

        logger.info(f"开始回测: {dates[0].strftime('%Y-%m-%d')} 至 {dates[-1].strftime('%Y-%m-%d')}")
        account_info = self.adapter.get_account_info()
        logger.info(f"初始资金: {account_info.cash:,.2f} 元")

        for i, today in enumerate(dates):
            if i < warmup_days:
                self._record_snapshot(today)
                self.daily_scores[today] = {}
                self.daily_selected[today] = []
                self.daily_early_scores[today] = 0.5
                continue

            self.adapter.set_current_date(today)
            account = self.adapter.get_account_info()
            if account is None:
                self._record_snapshot(today)
                continue

            # 盘尾交易模型：信号/仓位/成交全部锚定当天收盘价
            # （2026-08-26 小二陈修复：原先 open_price 优先会导致"收盘后决策、
            #  却用当天开盘价算仓位"——逆时间操作，违反盘尾交易原则）
            current_prices = {}
            for symbol in price_data.columns:
                if today in price_data.index:
                    val = price_data.loc[today, symbol]
                    if pd.isna(val):  # 停牌/数据缺失：跳过 NaN，避免下游 int(NaN) 崩溃
                        continue
                    current_prices[symbol] = float(val)

            holdings_dict = {}
            for pos in account.positions:
                holdings_dict[pos.symbol] = {
                    'shares': pos.shares,
                    'frozen_shares': 0,
                    'avg_cost': pos.avg_cost
                }

            hist_returns = returns.iloc[:i]
            hist_market = market_ret.iloc[:i]
            score_series = self.strategy.score_stocks(hist_returns, hist_market)


            score_series = self._scan_and_fuse_patterns(score_series, market_data, today)

            self._update_vote_weights()

            self._save_early_score_data(score_series, price_data, today, i, dates)

            # ---------- 大盘因子调制 ----------
            market_trend = 1.0
            if hasattr(market_data, 'benchmark_price') and not market_data.benchmark_price.empty:
                market_trend = self.factor_modulator.get_market_trend(market_data.benchmark_price.loc[hist_returns.index])

            if self.verbose:
                logger.debug(f"📊 大盘因子: 沪深300 MA20 {'向上 ✅' if market_trend == 1.0 else '向下 ❌'} (值: {market_trend})")
                if market_trend == 0.0:
                    logger.debug("   ⏳ 大盘向下，买入信号将被过滤")

            if hasattr(self, 'signal_modulator'):
                signal_df = pd.DataFrame({
                    'symbol': score_series.index,
                    'raw_score': score_series.values
                })
                modulated = self.signal_modulator.modulate_with_market(signal_df, market_trend)
                score_series = pd.Series(modulated['final_score'].values, index=modulated['symbol'])

            if not score_series.empty:
                factor_table = self.factor_modulator.get_factor_table(today, list(score_series.index))
                modulator_dict = factor_table.set_index('symbol')['modulator'].to_dict()
                final_scores = score_series * pd.Series(modulator_dict)
                final_scores = final_scores.fillna(score_series)
            else:
                final_scores = score_series

            buy_list = final_scores.head(self.top_n).index.tolist() if len(final_scores) > 0 else []
            self.daily_scores[today] = final_scores.head(self.top_n).to_dict()
            self.daily_selected[today] = buy_list

            self._execute_sells(holdings_dict, final_scores, market_data, account, current_prices, today, hist_returns, hist_market)

            self._execute_buys(buy_list, final_scores, market_data, account, current_prices, today)

            self._record_snapshot(today)

            if i % 50 == 0:
                acc = self.adapter.get_account_info()
                if self.verbose:
                    logger.debug(f"  {today.strftime('%Y-%m-%d')} 总资产: {acc.total_asset:,.2f} 元")

        self._extract_results(dates, auto_save)
        return self
