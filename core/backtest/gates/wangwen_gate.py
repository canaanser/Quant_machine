# -*- coding: utf-8 -*-
"""
王文五闸门（WangwenGate）—— 2026-09-02 P1 试点（等价替换，不重构）
=====================================================================
从 pipeline 搬来的逻辑（原 _precompute_ww_state/_ww_allows/_execute_ww_exit）：
  - 进场门槛 ww_min：买入票王文五项数 < ww_min → 不让买（基本面闸门）
  - 恶化退出 ww_exit：持仓票最新财报项数 ≤ ww_exit → 全卖（基本面认错）
无前视：每票 {披露日: 项数} 变化表，判定只消费 pubDate < today 的最近一期。
"""
from typing import Dict, Optional, Tuple

import pandas as pd

from .base import Gate


class WangwenGate(Gate):
    """王文五基本面闸门（进场门槛 + 持仓恶化退出）"""

    def __init__(self, ww_min: Optional[int] = None, ww_exit: Optional[int] = None):
        self.ww_min = ww_min       # 进场门槛：项数 < ww_min 不让买
        self.ww_exit = ww_exit     # 退出阈值：项数 ≤ ww_exit 全卖
        self._ww_state = {}        # {code: [(披露日, 项数)...]} 升序
        self._ww_sel = None

    @property
    def name(self) -> str:
        return "wangwen"

    @property
    def exit_priority(self) -> int:
        """王文五恶化退出：止损止盈后、策略卖出前（原 pipeline 顺序②b）"""
        return 20

    @property
    def active(self) -> bool:
        """有任一开关启用才算生效"""
        return self.ww_min is not None or self.ww_exit is not None

    # ---------- 数据准备（原 _precompute_ww_state） ----------
    def prepare(self, market_data) -> None:
        if not self.active:
            return
        from selection.wangwen import WangwenSelector
        self._ww_sel = WangwenSelector()
        self._ww_state = {}
        codes = list(market_data.price.columns)
        for code in codes:
            series = getattr(self._ww_sel, '_ind_series', {}).get(code)
            pts = []
            if series:
                for pub, _ in series:
                    try:
                        n = self._ww_sel.score_items(code, pub)['count']
                        pts.append((pub, n))
                    except Exception:
                        continue
            if pts:
                pts.sort()
                self._ww_state[code] = pts

    # ---------- 查询 ----------
    def _items_at(self, symbol: str, date) -> Optional[int]:
        """symbol 在 date 时点最近披露财报的王文五项数；无数据→None"""
        ts = pd.Timestamp(date)
        pts = self._ww_state.get(symbol)
        if not pts:
            return None
        past = [n for p, n in pts if p < ts]
        return past[-1] if past else None

    # ---------- 买入侧（原 _ww_allows） ----------
    def filter_buy_candidates(self, scores: pd.Series, date, holdings=None,
                              market_data=None) -> pd.Series:
        """进场门槛：项数 < ww_min 的候选剔除（无数据放行）"""
        if self.ww_min is None:
            return scores
        keep = [sym for sym in scores.index if self._allows_buy(sym, date)]
        return scores[scores.index.isin(keep)]

    def _allows_buy(self, symbol: str, date) -> bool:
        n = self._items_at(symbol, date)
        if n is None:
            return True  # 无财报数据 → 放行（不误杀）
        return n >= self.ww_min

    # ---------- 卖出侧（原 _execute_ww_exit 判定部分） ----------
    def should_exit(self, symbol: str, date, position: Dict,
                    market_data=None) -> Tuple[bool, str]:
        """持仓票最新财报项数 ≤ ww_exit → 退出（基本面认错）"""
        if self.ww_exit is None:
            return False, ""
        n = self._items_at(symbol, date)
        if n is None or n > self.ww_exit:
            return False, ""
        return True, f"王文五恶化({n}项)"
