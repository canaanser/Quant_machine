# -*- coding: utf-8 -*-
"""
选池/筛选器包（2026-08-30 小二陈，位于项目根目录）
===================================================
统一"选池筛选器"出口：每个筛选器产出当日可买名单，供回测/前端/其他 App 消费。

用法：
    from selection import WangwenSelector
    sel = WangwenSelector()
    names = sel.eligible('2026-08-27')          # 当日池名单
    names = sel.eligible('2026-08-27', codes=[...])  # 指定候选子集

以后新增筛选器：在 selection/ 下加文件（继承 BaseSelector），在此导出。
"""
from .base import BaseSelector
from .wangwen import WangwenSelector

__all__ = [
    'BaseSelector',
    'WangwenSelector',
]
