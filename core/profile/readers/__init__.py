# -*- coding: utf-8 -*-
"""
档案读取器集合（2026-08-30 老板：股票=人，数据=档案）
======================================================
每个 reader 只读一类档案，互不依赖（干湿分离：模块 = reader）。
"""
from .kline import KlineReader
from .fundamentals import FundamentalsReader
from .tags import TagsReader
from .meta import MetaReader

__all__ = ['KlineReader', 'FundamentalsReader', 'TagsReader', 'MetaReader']
