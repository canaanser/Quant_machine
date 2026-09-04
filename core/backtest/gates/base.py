# -*- coding: utf-8 -*-
"""
闸门（Gate）基类 —— 2026-09-02 老板架构整理（CPU 设计 + 小二陈审校）
=====================================================================
目标：pipeline 的横切闸门（趋势/王文五/大盘/标签）外移为独立对象，
      pipeline 只做时序编排。P1 阶段只切 WangwenGate（等价替换，不重构执行链）。

设计约定（审校后定版）：
  1. 接口最小：name / prepare / 买侧过滤 / 卖侧退出
  2. 买/卖分开：filter_buy_candidates（对候选过滤或降权）+ should_exit（对持仓判退出）
  3. market_data 可选参数（MarketGate 看大盘用，逐票 Gate 忽略）
  4. exit_priority 钉执行顺序（默认 100 排最后；P1 不用自动排序，pipeline 保持显式顺序）
  5. position 只依赖现有字段（shares/avg_cost），未来字段不阻塞实现
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple

import pandas as pd


class Gate(ABC):
    """闸门基类：每类闸门（趋势/王文五/大盘/标签）实现一个子类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """闸门名称，用于日志和调试"""
        raise NotImplementedError

    @property
    def exit_priority(self) -> int:
        """卖出侧执行优先级（数字越小越先）。默认 100=排最后。P1 不用自动排序。"""
        return 100

    def prepare(self, market_data) -> None:
        """回测前准备该闸门的数据表（可选，子类覆盖）"""
        pass

    # ===== 买入侧：对候选过滤/降权 =====
    def filter_buy_candidates(
        self,
        scores: pd.Series,
        date: pd.Timestamp,
        holdings: Dict[str, Dict],
        market_data=None,
    ) -> pd.Series:
        """买入侧过滤：返回处理后的 scores（默认原样返回，子类覆盖）"""
        return scores

    # ===== 卖出侧：对持仓判退出 =====
    def should_exit(
        self,
        symbol: str,
        date: pd.Timestamp,
        position: Dict,
        market_data=None,
    ) -> Tuple[bool, str]:
        """卖出侧判定：返回 (是否退出, 原因)。默认不退出。"""
        return False, ""
