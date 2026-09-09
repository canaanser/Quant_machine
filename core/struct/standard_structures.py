"""
标准数据结构定义
用于适配器层与核心引擎之间的数据传递
"""

from dataclasses import dataclass
from typing import List, Optional

@dataclass
class PositionInfo:
    """单只股票持仓信息"""
    symbol: str          # 股票代码 (如 "000063")
    name: str            # 股票名称
    shares: int          # 持仓数量 (股)
    avg_cost: float      # 持仓成本 (移动加权平均)
    current_price: float # 当前市价
    market_value: float  # 持仓市值 (shares * current_price)

@dataclass
class AccountInfo:
    """账户信息"""
    total_asset: float      # 总资产 (现金 + 持仓市值)
    cash: float             # 可用现金
    frozen_cash: float      # 冻结资金 (买入在途)
    positions: List[PositionInfo]  # 持仓列表
    timestamp: str          # 时间戳 ("YYYY-MM-DD HH:MM:SS")
