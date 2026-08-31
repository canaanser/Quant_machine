# -*- coding: utf-8 -*-
"""
股票档案·基类与读取器（2026-08-30 老板：股票=人，数据=档案）
==============================================================
干湿分离原则：
  - 功能 = core/profile/（组装逻辑）
  - 模块 = 各档案读取器（kline/fundamentals/tags/meta，各自独立）
  - 数据 = data/ 下各档案文件（互不合并）
  - 产物 = 虚拟组装结果（运行时生成，不落盘）

每个"档案读取器"是一个模块：只负责读一类档案，返回标准结构。
StockProfile 把多类档案按 code 组装成"一个人的全部档案"（逻辑视图）。
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class BaseProfileReader(ABC):
    """档案读取器基类：每类档案一个实现，只读一类数据"""

    #: 档案名（如 kline/fundamentals/tags/meta）
    name: str = "base"

    @abstractmethod
    def read(self, code: str, date=None, **kw):
        """读取单只股票某类档案。date=None 返回全量；否则返回该日视图"""
        raise NotImplementedError

    def read_many(self, codes: List[str], date=None, **kw) -> Dict[str, object]:
        """批量读取（默认逐票调用 read，子类可覆写优化）"""
        return {c: self.read(c, date=date, **kw) for c in codes}
