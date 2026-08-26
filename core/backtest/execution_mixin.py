# -*- coding: utf-8 -*-
"""
交易执行 Mixin（2026-08-26 小二陈：core/backtest.py 拆分为包）
职责：早盘评分数据保存、卖出执行、买入执行。
"""

import pandas as pd

from ..risk_manager import create_default_account, Position


class _ExecutionMixin:
    """交易执行逻辑（run 主循环内三段独立逻辑）"""

    def _save_early_score_data(self, score_series, price_data, today, i, dates):
        # ========== 早盘评分计算（纯旁路，不参与交易） ==========
        if i == len(dates) - 1:
            # 保存最后一天的均线数据，用于计算下一天的早盘评分
            self._last_ma5 = {}
            self._last_ma20 = {}
            self._last_close = {}
            for symbol in score_series.index[:self.top_n]:
                try:
                    if symbol in price_data.columns and today in price_data.index:
                        self._last_close[symbol] = price_data.loc[today, symbol]
                        self._last_ma5[symbol] = price_data[symbol].rolling(5).mean().loc[today] if len(price_data[symbol].dropna()) > 5 else self._last_close[symbol]
                        self._last_ma20[symbol] = price_data[symbol].rolling(20).mean().loc[today] if len(price_data[symbol].dropna()) > 20 else self._last_close[symbol]
                except Exception:
                    pass

    def _execute_sells(self, holdings_dict, final_scores, market_data, account, current_prices, today, hist_returns, hist_market):
        # ---------- 卖出逻辑 ----------
        # 调用策略自己的退出信号接口
        exit_series = self.strategy.get_exit_signal(hist_returns, hist_market)
        sell_signals = [sym for sym, should_exit in exit_series.items() if should_exit]

        for symbol in list(holdings_dict.keys()):
            if symbol in sell_signals:
                pos = holdings_dict[symbol]
                score = final_scores.get(symbol, 0.5)
                tag = market_data.info.loc[symbol].get('tag') if symbol in market_data.info.index and 'tag' in market_data.info.columns else None

                if self.verbose:
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
                                if self.verbose:
                                    print(f"   ✅ 卖出成交: {symbol} {status['filled_volume']}股 @ {status['filled_price']:.2f}，金额: {exec_report['filled_amount']:.2f}，总资产: {pnl:+.2f}")

    def _execute_buys(self, buy_list, final_scores, market_data, account, current_prices, today):
        # ---------- 买入 ----------
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
                            if self.verbose:
                                print(f"   ✅ 买入成交: {symbol} {status['filled_volume']}股 @ {status['filled_price']:.2f}，金额: {exec_report['filled_amount']:.2f}")
