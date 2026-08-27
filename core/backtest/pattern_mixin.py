# -*- coding: utf-8 -*-
"""
形态信号 Mixin（2026-08-26 小二陈：core/backtest.py 拆分为包）
职责：回测主循环中的形态扫描融合、每日投票权重更新。
"""

from core.logger import get_logger

logger = get_logger(__name__)


class _PatternScanMixin:
    """形态信号接入与权重更新（run 主循环内两段独立逻辑）"""

    def _load_pattern_index(self, symbols=None):
        """预加载 pattern_history → 内存索引 {(symbol, date): [形态]}（2026-08-28 小二陈）
        替代"回测每天现扫形态"：扫描器已建表（含先验 strength），回测查表 O(1)。
        优化（2026-08-28）：只加载回测涉及的股票（原全表 36.8 万行 → 数千行）。"""
        self._pattern_index = {}
        self._pattern_index_ok = False
        try:
            import sqlite3
            from config.config import PATTERN_DB_PATH
            if not PATTERN_DB_PATH.exists():
                logger.warning("⚠️ pattern_history.db 不存在，回测无形态信号（先跑扫描器）")
                return
            conn = sqlite3.connect(f"file:{PATTERN_DB_PATH}?mode=ro", uri=True)
            sql = "SELECT symbol, substr(match_date,1,10), pattern_id, category, strength FROM pattern_history"
            if symbols:
                ph = ",".join("?" * len(symbols))
                sql += f" WHERE symbol IN ({ph})"
                rows = conn.execute(sql, list(symbols)).fetchall()
            else:
                rows = conn.execute(sql).fetchall()
            conn.close()
            for symbol, date_str, pid, cat, strength in rows:
                self._pattern_index.setdefault((symbol, date_str), []).append({
                    'pattern_id': pid,
                    'category': cat or 'neutral',
                    'strength': float(strength) if strength is not None else 0.0,
                })
            self._pattern_index_ok = True
            logger.info("📚 形态信号索引预加载完成：%d 条 / %d 个(股票×日期)组合",
                        len(rows), len(self._pattern_index))
        except Exception as e:
            self._pattern_index_ok = False
            logger.warning("⚠️ 形态索引加载失败，回测将无形态信号: %s", e)

    def _scan_and_fuse_patterns(self, score_series, market_data, today):
        # ===== 形态信号接入策略层（2026-08-28：查表替代每天现扫） =====
        # 原实现每天 scan_patterns 现扫（5万次重复）+ 无波段位置信息；
        # 现查扫描器建好的 pattern_history（含先验 strength、无未来函数）
        if not getattr(self, '_pattern_index', None):
            self._load_pattern_index(list(score_series.index))
        if not getattr(self, '_pattern_index_ok', False):
            return score_series

        today_str = today.strftime('%Y-%m-%d') if hasattr(today, 'strftime') else str(today)

        # 修复（2026-08-28）：score_series 可能是 int64 dtype，写入 float 触发 pandas FutureWarning
        score_series = score_series.astype(float)

        for symbol in score_series.index:
            try:
                recs = self._pattern_index.get((symbol, today_str))
                if not recs:
                    continue
                best = max(recs, key=lambda r: r['strength'])
                pattern_strength = best['strength']
                if pattern_strength <= 0:
                    continue

                traditional_score = score_series.get(symbol, 0.0)
                # 方向权重（回测降级口径与旧版一致；后续可升级为位置级权重）
                from config.config import WEIGHT_SOURCE
                from structure_engine.signals.signal_weights import get_direction_weight
                direction = best.get('category', 'neutral')
                w = get_direction_weight(direction, source=WEIGHT_SOURCE)
                effective_strength = pattern_strength * w
                if effective_strength > 0:
                    fused_score = self.strategy.fuse_with_patterns(
                        traditional_score, effective_strength, w=0.3
                    )
                    score_series[symbol] = fused_score
                    if self.verbose:
                        logger.debug(f"   🔄 形态融合(查表): {symbol} 传统={traditional_score:.4f} + 形态×权重({w:.2f})={effective_strength:.4f} → {fused_score:.4f}")

            except Exception as e:
                if not hasattr(self, '_pattern_scan_warning_printed'):
                    if self.verbose:
                        logger.debug(f"   ⚠️ 形态融合跳过 {symbol}: {e}")
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
