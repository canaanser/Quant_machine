"""
模拟适配器 (SimulatedBrokerAdapter)
用于回测和模拟交易，从本地数据读取账户状态
"""

from datetime import datetime
from typing import Dict, Optional, List
import random
import pandas as pd

from .standard_structures import AccountInfo, PositionInfo
from .base_adapter import BrokerAdapter


class SimulatedBrokerAdapter(BrokerAdapter):
    """
    模拟适配器
    支持从本地数据源初始化账户，并模拟交易
    """
    
    def __init__(self, initial_cash: float = 500000.0, 
                 initial_positions: Dict[str, dict] = None,
                 price_data: pd.DataFrame = None):
        """
        :param initial_cash: 初始现金
        :param initial_positions: 初始持仓 {symbol: {"name": str, "shares": int, "avg_cost": float}}
        :param price_data: 价格数据（用于获取当前价格）
        """
        self.cash = initial_cash
        self.frozen_cash = 0.0
        self.positions: Dict[str, dict] = initial_positions or {}
        self.order_counter = 0
        self.pending_orders = {}
        self.price_data = price_data
        self._price_cache = {}
        self._current_date = None  # 当前日期，用于价格查询
        
        # 如果传入了价格数据，预加载价格
        if price_data is not None and not price_data.empty:
            self._load_prices_from_data()

    def _load_prices_from_data(self):
        """从DataFrame加载最新价格到缓存"""
        if self.price_data is None or self.price_data.empty:
            return
        # 取最后一行作为最新价格
        latest = self.price_data.iloc[-1]
        for symbol in self.price_data.columns:
            if not pd.isna(latest[symbol]) and latest[symbol] > 0:
                self._price_cache[symbol] = float(latest[symbol])

    def set_current_date(self, date):
        """设置当前日期，用于价格查询"""
        self._current_date = date

    def get_account_info(self) -> AccountInfo:
        """获取账户信息"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pos_list = []
        total_market_value = 0.0

        for symbol, data in self.positions.items():
            current_price = self._get_price(symbol)
            market_value = data["shares"] * current_price
            total_market_value += market_value
            pos_list.append(PositionInfo(
                symbol=symbol,
                name=data.get("name", symbol),
                shares=data["shares"],
                avg_cost=data["avg_cost"],
                current_price=current_price,
                market_value=market_value
            ))

        return AccountInfo(
            total_asset=self.cash + total_market_value,
            cash=self.cash,
            frozen_cash=self.frozen_cash,
            positions=pos_list,
            timestamp=now
        )

    def place_order(self, symbol: str, action: str, volume: int, price_limit: Optional[float] = None, trade_date=None) -> str:
        """模拟下单（立即成交）"""
        order_id = f"SIM_{self.order_counter:06d}"
        self.order_counter += 1
        
        current_price = self._get_price(symbol)
        
        if action == "BUY":
            cost = volume * current_price
            if cost > self.cash:
                return f"ERROR: 资金不足 (需要 {cost:.2f}, 可用 {self.cash:.2f})"
            self.cash -= cost
            self.frozen_cash += cost
            
            # 更新持仓
            if symbol not in self.positions:
                self.positions[symbol] = {"name": symbol, "shares": 0, "avg_cost": 0}
            pos = self.positions[symbol]
            total_cost = pos["shares"] * pos["avg_cost"] + cost
            pos["shares"] += volume
            pos["avg_cost"] = total_cost / pos["shares"] if pos["shares"] > 0 else 0
            
        else:  # SELL
            if symbol not in self.positions:
                return f"ERROR: 无持仓 {symbol}"
            pos = self.positions[symbol]
            if pos["shares"] < volume:
                return f"ERROR: 持仓不足 (需要 {volume}, 持有 {pos['shares']})"
            pos["shares"] -= volume
            self.cash += volume * current_price
            if pos["shares"] == 0:
                del self.positions[symbol]

        self.pending_orders[order_id] = {
            "symbol": symbol,
            "action": action,
            "volume": volume,
            "price": current_price,
            "status": "FILLED",
            "submitted_at": trade_date.isoformat() if trade_date else datetime.now().isoformat()
        }
        return order_id

    def get_order_status(self, order_id: str) -> dict:
        """获取订单状态"""
        if order_id not in self.pending_orders:
            return {"status": "NOT_FOUND", "filled_price": 0.0, "filled_volume": 0}
        order = self.pending_orders[order_id]
        return {
            "status": order["status"],
            "filled_price": order["price"],
            "filled_volume": order["volume"]
        }

    def get_current_price(self, symbol: str) -> float:
        """获取当前市价"""
        return self._get_price(symbol)

    def _get_price(self, symbol: str) -> float:
        """根据当前日期从 price_data 获取价格"""
        # 如果有 price_data 和当前日期，从数据中读取
        if hasattr(self, 'price_data') and self.price_data is not None:
            if hasattr(self, '_current_date') and self._current_date is not None:
                if symbol in self.price_data.columns:
                    val = self.price_data.loc[self._current_date, symbol]
                    if not pd.isna(val) and val > 0:
                        return float(val)
        # 回退到缓存
        if symbol in self._price_cache and self._price_cache[symbol] > 0:
            return self._price_cache[symbol]
        return 50.0