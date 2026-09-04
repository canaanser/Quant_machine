# -*- coding: utf-8 -*-
"""
标签路由器最小版（TagRouter）—— 2026-09-02 架构整理 P1 后半
=================================================================
职责：按股票标签决定"是否跳过某闸门"。P1 只实现一个功能：
      震荡票跳过趋势门（原 pipeline 的 trend_gate_split 逻辑）。
接口留扩展：未来可接更多标签（王文五/市值/滚动标签）做复杂路由。

设计约定：
  - 只做"跳过判定"，不做完整路由框架（不过度设计）
  - 标签数据静态加载（v1），待标签滚动化后改 prepare 内数据源即可
"""
from typing import Optional, Set

import pandas as pd


class TagRouter:
    """标签路由器：判断某票在某日是否应跳过某闸门"""

    def __init__(self):
        self._osc_codes: Set[str] = set()   # 震荡票代码集合
        self._loaded = False

    @property
    def name(self) -> str:
        return "tag_router"

    def prepare(self, market_data=None) -> None:
        """加载震荡票标签（v1 静态分类）"""
        import os
        from config.config import PROJECT_ROOT, TAGS_DATA_DIR
        try:
            p = os.path.join(PROJECT_ROOT, TAGS_DATA_DIR, 'oscillation_v1.csv')
            df = pd.read_csv(p, dtype={'code': str})
            df['code'] = df['code'].str.zfill(6)
            self._osc_codes = set(df[df['value'] == '震荡票']['code'])
        except Exception:
            self._osc_codes = set()
        self._loaded = True

    def should_skip_gate(self, symbol: str, date=None, gate_name: str = None) -> bool:
        """判断该票当日是否应跳过指定闸门。
        P1 实现：震荡票跳过趋势门（trend_gate_split）。其余返回 False。"""
        if gate_name == "trend_gate":
            return symbol in self._osc_codes
        return False

    def is_oscillation(self, symbol: str) -> bool:
        """该票是否为震荡票（便捷查询）"""
        return symbol in self._osc_codes
