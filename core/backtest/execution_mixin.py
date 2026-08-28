# -*- coding: utf-8 -*-
"""
交易执行 Mixin（2026-08-26 小二陈：core/backtest.py 拆分为包）
职责：早盘评分数据保存、卖出执行、买入执行。
"""

import pandas as pd

from core.logger import get_logger
from ..risk_manager import create_default_account, Position

logger = get_logger(__name__)


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

    def _execute_stop_loss(self, holdings_dict, current_prices, today):
        """机械止损（判定在封控层 risk_manager.evaluate_exits，2026-08-29 老板：封控层全权）
        止损=认错：企稳后抄底仍跌超止损线=抄错底，最高优先级全卖——不扛抄错的单。
        成交=T日收盘价（尾盘最后一秒）"""
        if not self.risk_manager.stop_loss_pct:
            return
        for order in self.risk_manager.evaluate_exits(holdings_dict, current_prices, today):
            if order['reason'] == '机械止损(认错)':
                price = current_prices.get(order['symbol'])
                self._sell(order['symbol'], order['target_volume'], price, today, order['reason'])
                if self.verbose:
                    logger.debug(f"🛑 机械止损(认错): {order['symbol']} 全清 @ {price:.2f}")

    def _execute_take_profit(self, holdings_dict, current_prices, today):
        """止盈（判定在封控层，卖一半锁利润——盈利垫子）；T+1 成交价"""
        if not self.risk_manager.take_profit_pct:
            return
        for order in self.risk_manager.evaluate_exits(holdings_dict, current_prices, today):
            if order['reason'] == '止盈锁利':
                price = current_prices.get(order['symbol'])
                self._sell(order['symbol'], order['target_volume'], price, today, order['reason'])
                if self.verbose:
                    logger.debug(f"🟢 止盈锁利: {order['symbol']} 卖{order['target_volume']}股 @ {price:.2f}")

    def _in_protection(self, symbol, pos, today):
        """保护期：判定在封控层（人买入 N 日策略信号不卖，止损/止盈照常）"""
        return self.risk_manager.in_protection(pos, today)

    def _sell(self, symbol, shares, price, today, reason=''):
        """统一卖出执行（2026-08-28）；price 传入作为成交价（T 日收盘价，尾盘）"""
        if shares <= 0:
            return
        order_id = self.adapter.place_order(symbol, 'SELL', shares, price_limit=price, trade_date=today)
        if not order_id.startswith('ERROR'):
            status = self.adapter.get_order_status(order_id)
            if status['status'] == 'FILLED':
                exec_report = {
                    'order_id': order_id, 'symbol': symbol, 'action': 'SELL',
                    'filled_volume': status['filled_volume'],
                    'filled_amount': status['filled_volume'] * status['filled_price'],
                    'commission': 0, 'fill_price': status['filled_price'],
                    'timestamp': pd.Timestamp(today),
                    'total_position': self._total_position_after_trade(),  # 该笔后总仓位（无歧义：持仓市值/总资产）
                }
                self.performance_analyzer.record_trade(exec_report)
                return exec_report
        return None

    def _total_position_after_trade(self) -> float:
        """该笔交易完成后的总仓位 = 持仓总市值 / (现金 + 持仓市值)（2026-08-29 老板要求，无歧义）
        直接用 adapter.positions（dict{shares,avg_cost}）+ adapter.cash——get_account_info 返回对象列表无法 .get"""
        try:
            pos_value = 0.0
            for sym, p in self.adapter.positions.items():
                shares = p.get('shares', 0)
                if shares > 0:
                    px = self.adapter._get_price(sym)
                    if not px or px <= 0:
                        px = p.get('avg_cost', 0)
                    pos_value += shares * px
            cash = self.adapter.cash
            total = cash + pos_value
            return round(pos_value / total, 4) if total > 0 else 0.0
        except Exception:
            return 0.0

    def _execute_sells(self, holdings_dict, final_scores, market_data, account, current_prices, today, hist_returns, hist_market):
        # ---------- 策略卖出逻辑（2026-08-28 方案2：死叉真假由封控层判）----------
        # 死叉=候选卖点（可能底背离/浮盈/小反转）→ 封控层 judge_deadcross_exit 判真假才执行
        # 评分基于T-1日数据（昨日评分），成交=T日收盘价（尾盘）
        exit_info = self.strategy.get_exit_signal(hist_returns, hist_market)
        sell_signals = [sym for sym, info in exit_info.items() if info.get('exit')]

        for symbol in list(holdings_dict.keys()):
            if symbol not in sell_signals:
                continue
            pos = holdings_dict[symbol]
            if self._in_protection(symbol, pos, today):
                if self.verbose:
                    logger.debug(f"🛡️ 保护期: {symbol} 策略信号暂不执行（人买入观察期）")
                continue
            # 封控层判死叉真假（2026-08-28 老板：死叉可能是底背离/浮盈/小反转）
            price = current_prices.get(symbol, 0)
            if not price or pos['shares'] <= 0:
                continue
            pnl = (price - pos.get('avg_cost', 0)) / pos.get('avg_cost', 1) if pos.get('avg_cost') else 0
            info = exit_info.get(symbol, {})
            should_sell, reason = self.risk_manager.judge_deadcross_exit(
                pnl, info.get('pct_250d_high'), info.get('bottom_divergence', False))
            if not should_sell:
                if self.verbose:
                    logger.debug(f"🔍 死叉被封控层驳回: {symbol}（{reason}）")
                continue
            if self.verbose:
                logger.debug(f"🔔 {reason}: {symbol} 持仓={pos['shares']}股")
            score = final_scores.get(symbol, 0.5)
            tag = market_data.info.loc[symbol].get('tag') if symbol in market_data.info.index and 'tag' in market_data.info.columns else None
            # 成交价 = T+1（无 T+1 价则退回 T 日）
            fill_price = price  # T 日收盘价（尾盘成交）

            if self.batch_exit:
                # 分批退出：死叉卖 1/3（剩余等后续信号/止损；铁律止损仍全清）
                sell_shares = max(100, int(pos['shares'] * 0.34 // 100) * 100)
                if sell_shares >= pos['shares']:
                    sell_shares = pos['shares']
                if self.verbose:
                    logger.debug(f"🔔 分批退出: {symbol} 卖{sell_shares}/{pos['shares']}股 (评分{score:.4f})")
                self._sell(symbol, sell_shares, fill_price, today, '死叉分批')
            else:
                if self.verbose:
                    logger.debug(f"🔔 死叉信号触发卖出: {symbol}, 持仓={pos['shares']}股, 评分={score:.4f}")
                self._sell(symbol, pos['shares'], fill_price, today, '死叉清仓')

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
                    signal, temp_account, current_prices.get(symbol, 0.0)
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
                                    'timestamp': pd.Timestamp(today),
                                    'total_position': self._total_position_after_trade(),  # 该笔后总仓位（2026-08-29 老板：SELL行也要有）
                                }
                                self.performance_analyzer.record_trade(exec_report)
                                pnl = (status['filled_price'] - avg_cost) * status['filled_volume']
                                if self.verbose:
                                    logger.debug(f"   ✅ 卖出成交: {symbol} {status['filled_volume']}股 @ {status['filled_price']:.2f}，金额: {exec_report['filled_amount']:.2f}，总资产: {pnl:+.2f}")

    def _execute_buys(self, buy_list, final_scores, market_data, account, current_prices, today):
        # ---------- 买入 ----------
        for symbol in buy_list:
            score = final_scores.get(symbol, 0.5)
            tag = market_data.info.loc[symbol].get('tag') if symbol in market_data.info.index and 'tag' in market_data.info.columns else None
            # 2026-08-29 修复：价格缺失（停牌/数据空洞）跳过不买——禁用默认 50 假交易（中钨高新 2024-01 50元假买致-1.2万假亏）
            if symbol not in current_prices or not current_prices.get(symbol):
                if self.verbose:
                    logger.debug(f"⏭️ {symbol} 当日无价格（停牌/缺失），跳过买入")
                continue
            current_price = current_prices.get(symbol)

            pos_info = None
            for pos in account.positions:
                if pos.symbol == symbol:
                    pos_info = pos
                    break
            if self.verbose:
                logger.debug(f"   🔎 买入前: {symbol} pos_info={'有'+str(pos_info.shares) if pos_info else '无'}"
                             f" account.positions={len(account.positions)}只")

            temp_account = create_default_account(account.cash)
            if pos_info:
                temp_account.positions[symbol] = Position(
                    shares=pos_info.shares,
                    frozen_shares=0,
                    avg_cost=pos_info.avg_cost
                )
            temp_account.total_asset = account.total_asset

            signal = {'symbol': symbol, 'action': 'BUY', 'score': score, 'tag': tag}
            # 2026-08-29 老板：买入不额外拒买（涨不怕+机械止损兜底）——靠质量/位置/筑底筛选
            approved = self.risk_manager.approve_order(
                signal, temp_account, current_price
            )
            if approved:
                volume = approved['target_volume']
                if volume > 0:
                    # 成交=T 日收盘价（尾盘最后一秒）；评分基于 T-1 日
                    fill_price = current_price  # T 日收盘价（尾盘成交）
                    order_id = self.adapter.place_order(symbol, 'BUY', volume, price_limit=fill_price, trade_date=today)
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
                                'timestamp': pd.Timestamp(today),
                                'total_position': self._total_position_after_trade(),  # 该笔后总仓位
                            }
                            self.performance_analyzer.record_trade(exec_report)
                            # 买入来源标记（2026-08-28：保护期需区分 人/系统 买入）
                            if symbol in self.adapter.positions:
                                self.adapter.positions[symbol]['buy_source'] = 'system'
                                self.adapter.positions[symbol]['buy_date'] = str(pd.Timestamp(today).date())
                            if self.verbose:
                                logger.debug(f"   ✅ 买入成交: {symbol} {status['filled_volume']}股 @ {status['filled_price']:.2f}，金额: {exec_report['filled_amount']:.2f}")
