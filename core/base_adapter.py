"""
适配器接口定义
所有券商/数据源适配器必须实现此接口
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from .standard_structures import AccountInfo, PositionInfo

class BrokerAdapter(ABC):
    """券商适配器基类"""
    
    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """获取账户信息（含持仓和资金）"""
        pass

    @abstractmethod
    def place_order(self, symbol: str, action: str, volume: int, 
                    price_limit: Optional[float] = None) -> str:
        """
        下单
        :param symbol: 股票代码
        :param action: "BUY" 或 "SELL"
        :param volume: 股数
        :param price_limit: 限价 (可选)，None 表示市价单
        :return: 订单号
        """
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> dict:
        """
        获取订单状态
        :return: {"status": "FILLED"/"PENDING"/"CANCELLED",
                  "filled_price": float, "filled_volume": int}
        """
        pass

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """获取当前市价"""
        pass
