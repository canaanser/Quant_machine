# -*- coding: utf-8 -*-
"""
回测流水线主类（2026-08-26 小二陈：core/backtest.py 拆分为包）
组合：_BacktestBase（初始化/结果/指标）+ _PatternScanMixin（形态/权重）
      + _ExecutionMixin（评分/买卖执行）。
run() 主循环骨架：段落逻辑已下沉到各 Mixin 的私有方法。
"""

import logging

import pandas as pd

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

    def __init__(self, strategy, top_n=10, commission=COMMISSION, risk_config=None, verbose: bool = False,
                 stop_loss_pct: float = None, take_profit_pct: float = None,
                 batch_exit: bool = False, protect_days: int = 0,
                 market_gate: str = None, gate_crash: float = -0.03, gate_ma200_half: bool = True,
                 old_sell: bool = False, trend_gate: str = None):
        super().__init__(strategy, top_n=top_n, commission=commission,
                         risk_config=risk_config, verbose=verbose, stop_loss_pct=stop_loss_pct,
                         take_profit_pct=take_profit_pct, batch_exit=batch_exit, protect_days=protect_days,
                         old_sell=old_sell)
        # 趋势线买入过滤器（2026-08-30 老板：做法二/三，先关止损测）
        #   None   = 不过滤（原行为）
        #   'week' = 周线趋势门：价站在周线上升趋势线上方才允许买（做法二）
        #   'month'= 月线趋势门（做法二，更大级别）
        #   'multi'= 多级别共振（做法三：月+周+日 各自判上升，≥threshold 才买）
        self.trend_gate = trend_gate
        self.trend_gate_threshold = 2  # multi 模式：几级向上才放行（默认≥2级）
        self._trend_state = None  # 预计算：{code: pd.Series(周期末→状态)}
        # 大盘风控开关（2026-08-28 小二陈）：'crash'=单日暴跌不开仓；'ma200'=大盘MA200下方半仓；'both'
        self.market_gate = market_gate
        self.gate_crash = gate_crash
        self.gate_ma200_half = gate_ma200_half
        # verbose=True 时，本包 logger 提升到 DEBUG 级（调试细节可见，保持原有行为）
        if verbose:
            logging.getLogger("core.backtest").setLevel(logging.DEBUG)

    def run(self, market_data: metadata, initial_cash: float = None, auto_save: bool = True,
            initial_positions: dict = None, trade_start=None):
        """initial_positions: 断点续跑用——实盘当前持仓 {symbol: {"shares": n, "avg_cost": p}}
        trade_start: 断点续跑用——该日期之前只 warmup 不交易（2026-08-28 小二陈）"""
        import time as _time
        _t0 = _time.time()
        if initial_cash is None:
            initial_cash = INITIAL_CASH

        price_data = market_data.price
        market_ret_raw = market_data.benchmark

        market_data.validate()
        returns = price_data.pct_change(fill_method=None).dropna(how='all')
        market_ret = market_ret_raw.pct_change(fill_method=None).dropna()
        common_idx = returns.index.intersection(market_ret.index)
        returns = returns.loc[common_idx]
        market_ret = market_ret.loc[common_idx]
        dates = common_idx

        # 策略预计算钩子（2026-08-28 小二陈）：SimpleStrategy 等可一次性预计算
        # 全历史因果特征矩阵，回测主循环每天 O(1) 查表（原每天重算 O(N²)，84只10年≈100分钟）
        if hasattr(self.strategy, 'prepare'):
            kw = {}
            if hasattr(market_data, 'volume') and market_data.volume is not None and not market_data.volume.empty:
                kw['volume'] = market_data.volume  # 质量评分（深跌+放量）需要量比
            self.strategy.prepare(returns, market_ret, **kw)

        # 趋势线过滤器预计算（2026-08-30 老板：做法二/三，无前视周期状态表）
        if self.trend_gate:
            self._precompute_trend_state(market_data)

        if hasattr(self.strategy, 'window') and hasattr(self.strategy, 'lookback'):
            warmup_days = self.strategy.window + self.strategy.lookback
        else:
            warmup_days = 60 + 20

        if len(dates) < warmup_days:
            raise ValueError(f"数据长度不足，需要 {warmup_days} 天，实际 {len(dates)} 天")

        initial_positions = initial_positions or {}  # 断点续跑：实盘持仓导入
        # 人持仓标记（2026-08-28：initial_positions=实盘人买入，保护期生效）
        for sym, p in initial_positions.items():
            p.setdefault('buy_source', 'human')
            p.setdefault('buy_date', str(pd.Timestamp(trade_start or dates[0]).date()))
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

            # 断点续跑：trade_start 之前只记录快照不交易（2026-08-28 小二陈）
            if trade_start is not None and today < pd.Timestamp(trade_start):
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

            # 盘尾交易模型（2026-08-29 老板定：无限接近尾盘最后一秒）
            # 评分/信号只用 T-1 日及之前数据（hist_returns 不含今天）——尾盘时 T 日未收盘，只能用昨日评分；
            # 成交用 T 日收盘价（尾盘最后一秒，收盘价已定）——不是未来函数。
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

            # 2026-08-29 老板：评分只用昨日(T-1)及之前数据——尾盘时T日未收盘，用昨日评分决策
            hist_returns = returns.iloc[:max(0, i - 1)]
            hist_market = market_ret.iloc[:max(0, i - 1)]
            score_series = self.strategy.score_stocks(hist_returns, hist_market)


            score_series = self._scan_and_fuse_patterns(score_series, market_data, today)

            self._update_vote_weights()

            self._save_early_score_data(score_series, price_data, today, i, dates)

            # ---------- 大盘因子调制 ----------
            market_trend = 1.0
            if hasattr(market_data, 'benchmark_price') and not market_data.benchmark_price.empty:
                market_trend = self.factor_modulator.get_market_trend(market_data.benchmark_price.loc[hist_returns.index])

            if self.verbose and i % 50 == 0:   # 降频（2026-08-28：原来每天一条，2500 天刷屏拖慢）
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

            # ---------- 大盘风控开关（2026-08-28 小二陈）----------
            # 回撤控制核心：单日暴跌不开新仓 / 大盘MA200下方半仓。
            # 与"个股止损"不同——不打断抄底周期，只在系统性风险时降仓（抄底策略的正确风控）。
            if self.market_gate and not final_scores.empty:
                gate = self._market_risk_gate(market_ret, market_data, today, i)
                if gate < 1.0:
                    final_scores = final_scores * gate
                    if self.verbose:
                        logger.debug(f"   🛡️ 大盘风控: gate={gate} ({today.date()})")

            if self.trend_gate and not final_scores.empty:
                allowed = [sym for sym in final_scores.index if self._trend_allows(sym, today)]
                final_scores = final_scores[final_scores.index.isin(allowed)]
                if self.verbose and len(allowed) < len(final_scores):
                    logger.debug(f"   📉 趋势线过滤器: {today.date()} 拦截 {len(final_scores) - len(allowed)} 只")

            buy_list = final_scores.head(self.top_n).index.tolist() if len(final_scores) > 0 else []
            self.daily_scores[today] = final_scores.head(self.top_n).to_dict()
            self.daily_selected[today] = buy_list

            self._execute_stop_loss(holdings_dict, current_prices, today)    # ① 铁律止损（最高优先级）

            self._execute_take_profit(holdings_dict, current_prices, today)  # ② 止盈（≥2×止损，卖半锁利润）

            self._execute_sells(holdings_dict, final_scores, market_data, account, current_prices, today, hist_returns, hist_market)  # ③ 策略信号（分批/保护期）

            self._execute_buys(buy_list, final_scores, market_data, account, current_prices, today)

            self._record_snapshot(today)

            if i % 50 == 0:
                acc = self.adapter.get_account_info()
                if self.verbose:
                    logger.debug(f"  {today.strftime('%Y-%m-%d')} 总资产: {acc.total_asset:,.2f} 元")

        self._extract_results(dates, auto_save)
        logger.info("⏱️ 回测完成：%s 至 %s，耗时 %.2f 秒",
                    dates[0].strftime('%Y-%m-%d'), dates[-1].strftime('%Y-%m-%d'),
                    _time.time() - _t0)
        return self

    def _precompute_trend_state(self, market_data):
        """趋势线状态预计算：每票建"周期末→状态"表（无前视）。

        week/month: 单级别门。multi: 月+周+日 三级打分。
        数据用 market_data 的 OHLCV（与回测同源，无未来数据）。
        """
        from core.trendline.state import period_state_map, multi_level_score
        self._trend_state = {}
        self._trend_score = {}
        freq = 'W-FRI' if self.trend_gate == 'week' else ('ME' if self.trend_gate == 'month' else None)
        codes = [c for c in market_data.price.columns
                 if c in market_data.price.columns]
        ohlc = self._build_ohlc_frames(market_data, codes)
        for code in codes:
            df = ohlc[code]
            if df is None or len(df) < 30:
                continue
            if freq:
                self._trend_state[code] = period_state_map(df, freq=freq)
            else:  # multi
                self._trend_score[code] = multi_level_score(df)

    def _build_ohlc_frames(self, market_data, codes):
        """从 metadata 抽每票 OHLC DataFrame（trendline 检测需要 high/low）"""
        import pandas as pd
        out = {}
        for code in codes:
            try:
                close = market_data.price[code]
                df = pd.DataFrame({'close': close})
                for col, src in (('open', 'open_price'), ('high', 'high_price'),
                                 ('low', 'low_price'), ('volume', 'volume')):
                    m = getattr(market_data, src, None)
                    if m is not None and code in m.columns:
                        df[col] = m[code]
                if 'high' not in df or df['high'].isna().all():
                    df['high'] = df['close']
                if 'low' not in df or df['low'].isna().all():
                    df['low'] = df['close']
                df = df.dropna(subset=['close'])
                out[code] = df
            except Exception:
                out[code] = None
        return out

    def _trend_allows(self, symbol, today) -> bool:
        """T 日该票是否通过趋势门。无状态/数据不足 → 放行（False 不拦截的保守策略会踏空，
        故用"没有足够数据就放行"，有状态才严格判）"""
        import pandas as pd
        ts = pd.Timestamp(today)
        if self.trend_gate in ('week', 'month'):
            s = self._trend_state.get(symbol)
            if s is None or len(s) == 0:
                return True
            past = s[s.index < ts]  # 只消费严格早于 T 的周期（杜绝周内偷看）
            if len(past) == 0:
                return True
            return bool(past.iloc[-1])
        if self.trend_gate == 'multi':
            sc = self._trend_score.get(symbol)
            if sc is None or len(sc) == 0:
                return True
            past = sc[sc.index < ts]
            if len(past) == 0:
                return True
            return int(past.iloc[-1]) >= self.trend_gate_threshold
        return True

    def _market_risk_gate(self, market_ret, market_data, today, i):
        """大盘风控开关（2026-08-28 小二陈）：
        返回买入乘数：0=当日不开新仓（单日暴跌），0.5=半仓（大盘MA200下方），1=正常。
        只影响新买入，不打断已有持仓的抄底周期。"""
        gate = 1.0
        # 单日暴跌：大盘当日收益 ≤ gate_crash → 当日禁止新开仓
        if self.market_gate in ('crash', 'both'):
            try:
                if today in market_ret.index:
                    r = float(market_ret.loc[today])
                    if r <= self.gate_crash:
                        gate = 0.0
            except Exception:
                pass
        # 大盘 MA200 下方 → 半仓
        if self.market_gate in ('ma200', 'both') and gate > 0:
            try:
                bp = market_data.benchmark_price
                if bp is not None and not bp.empty and today in bp.index:
                    hist = bp.loc[:today]
                    ma200 = hist.rolling(200, min_periods=100).mean().iloc[-1]
                    if not pd.isna(ma200) and hist.iloc[-1] < ma200:
                        gate = min(gate, 0.5)
            except Exception:
                pass
        return gate
