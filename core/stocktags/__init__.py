# 职责: 形态/信号原子标签; 只被 alpha/strategy 消费, profile 只读; 不独立决策
# -*- coding: utf-8 -*-
"""
标签系统包（2026-08-30 老板：标签归类系统）
============================================
统一"标签"出口：标签池（registry）+ 生成器（generators/）+ 消费引擎（engine）。

用法：
    from core.stocktags import produce, tag_at, filter, assemble, hierarchy, list_tags
    produce('oscillation')                                   # 生成震荡度标签并落盘
    tag_at('000063', '2026-08-28', 'oscillation')            # -> '震荡票'
    filter(None, '2026-08-28', oscillation='震荡票')         # -> ['000063', ...]
    hierarchy('oscillation', 'wangwen', '2026-08-28')        # 层级组装

新标签方案：在 core/tags/generators/ 加文件继承 BaseTagGenerator，即插即用。
"""
from .base import BaseTagGenerator, TAG_COLUMNS
from .registry import register, unregister, get, list_tags
from .engine import (load, produce, backfill, tag_at, filter,
                     assemble, hierarchy)

__all__ = [
    'BaseTagGenerator', 'TAG_COLUMNS',
    'register', 'unregister', 'get', 'list_tags',
    'load', 'produce', 'backfill', 'tag_at', 'filter',
    'assemble', 'hierarchy',
]
