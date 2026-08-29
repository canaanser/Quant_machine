# -*- coding: utf-8 -*-
"""
选池/筛选器基类（2026-08-30 小二陈）
=====================================
统一"选池筛选器"接口：输入日期，输出当日可买股票名单（list[str]）。
前端/回测/其他 App 均通过此接口消费名单——与具体筛选逻辑解耦。

设计动机（老板 2026-08-30）：
  - 以后可能添加不同筛选器（王文五/全市场/行业/质量……），每个筛选器产出一份名单
  - 名单像 config 里的静态池子一样可被任意调用方使用，但筛选器本身是动态生成的
  - 核心引擎（backtest）保持通用，不感知任何筛选器——筛选器产出名单，引擎消费名单
"""
from abc import ABC, abstractmethod
from typing import List, Optional


class BaseSelector(ABC):
    """选池筛选器基类：统一接口 run(date) -> 当日可买名单"""

    #: 筛选器名称（报告/诊断用，子类覆盖）
    name: str = "base"

    @abstractmethod
    def eligible(self, date, codes: Optional[List[str]] = None) -> List[str]:
        """返回 date 当日符合本筛选器标准的代码列表。

        Args:
            date: 交易日（pd.Timestamp / str / datetime 均可）
            codes: 候选代码子集；None=全部已加载标的

        Returns:
            当日可买代码列表（list[str]）
        """
        raise NotImplementedError

    def run(self, date, codes: Optional[List[str]] = None) -> List[str]:
        """别名：与 eligible 同义（调用方语义更直观）"""
        return self.eligible(date, codes=codes)

    def describe(self) -> str:
        """筛选器说明（一行，报告用）"""
        return f"{self.name}（{self.__class__.__doc__ or ''}）"
