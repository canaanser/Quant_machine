# -*- coding: utf-8 -*-
"""
形态信号 Mixin（2026-08-26 小二陈：core/backtest.py 拆分为包）
职责：回测主循环中的形态扫描融合、每日投票权重更新。
"""

from core.logger import get_logger

logger = get_logger(__name__)


class _PatternScanMixin:
    """形态扫描与权重更新（run 主循环内两段独立逻辑）"""

    def _scan_and_fuse_patterns(self, score_series, market_data, today):
        # ===== 形态信号接入策略层 =====
        from structure_engine.scanner import scan_patterns

        for symbol in score_series.index:
            # 修复：原来无条件打印刷屏，改为仅 verbose 模式输出
            if self.verbose:
                logger.debug(f"🔍 形态扫描入口: {symbol}, verbose={self.verbose}")
            try:
                ohlc = market_data.get_ohlc(symbol)
                if ohlc is None or ohlc.empty:
                    continue

                # 性能优化（2026-08-26 小二陈）：形态扫描只取最近窗口
                # 原实现 hist_ohlc = ohlc.loc[:today] 每天扫全历史 → O(N²)
                # 形态是局部的（窗口≤5根）+ 回测只取当天信号 → 60 根窗口足够，O(N²)→O(N)
                SCAN_WINDOW = 60  # 交易日
                try:
                    today_pos = ohlc.index.get_loc(today)
                    start_pos = max(0, today_pos - SCAN_WINDOW)
                    hist_ohlc = ohlc.iloc[start_pos:today_pos + 1]
                except (KeyError, TypeError):
                    hist_ohlc = ohlc.loc[:today]  # 兜底：找不到 today 时退回全历史
                if len(hist_ohlc) < 5:
                    continue

                scan_results = scan_patterns(hist_ohlc, debug=self.verbose)

                pattern_strength = 0.0
                today_str = today.strftime('%Y-%m-%d') if hasattr(today, 'strftime') else str(today)

                for r in scan_results:
                    r_date = r.get('date', '')
                    if r_date == today_str:
                        strength = r.get('strength', 0.0)
                        if strength > pattern_strength:
                            pattern_strength = strength

                if pattern_strength > 0:
                    traditional_score = score_series.get(symbol, 0.0)
                    # 位置权重接入（方向级降级：回测当前无波段位置信息；
                    # 权重来源由 config.WEIGHT_SOURCE 控制：legacy=现有表 / data=数据驱动表）
                    from config.config import WEIGHT_SOURCE
                    from structure_engine.signals.signal_weights import get_direction_weight
                    direction = r.get('category', 'neutral')
                    w = get_direction_weight(direction, source=WEIGHT_SOURCE)
                    effective_strength = pattern_strength * w
                    if effective_strength > 0:
                        fused_score = self.strategy.fuse_with_patterns(
                            traditional_score, effective_strength, w=0.3
                        )
                        score_series[symbol] = fused_score
                        if self.verbose:
                            logger.debug(f"   🔄 形态融合: {symbol} 传统={traditional_score:.4f} + 形态×权重({w:.2f})={effective_strength:.4f} → {fused_score:.4f}")

            except Exception as e:
                if not hasattr(self, '_pattern_scan_warning_printed'):
                    if self.verbose:
                        logger.debug(f"   ⚠️ 形态扫描跳过 {symbol}: {e}")
                    self._pattern_scan_warning_printed = True
                continue
        return score_series

    def _update_vote_weights(self):
        # ===== 每日权重更新（从投票池获取排名） =====
        try:
            from structure_engine.voting.vote_pool import VotePool
            from config import PATTERN_MIN_SAMPLES, PATTERN_WEIGHT_LEARNING_RATE

            vote_pool = VotePool()
            top_rankings = vote_pool.get_top_n(n=20, min_occurrences=PATTERN_MIN_SAMPLES)
            if top_rankings:
                self.factor_modulator.update_weights(
                    top_rankings,
                    learning_rate=PATTERN_WEIGHT_LEARNING_RATE,
                    min_samples=PATTERN_MIN_SAMPLES
                )
        except Exception as e:
            if not hasattr(self, '_weight_update_warning'):
                if self.verbose:
                    logger.debug(f"   ⚠️ 权重更新跳过: {e}")
                self._weight_update_warning = True
