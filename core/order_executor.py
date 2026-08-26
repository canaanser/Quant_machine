"""
执行层 (Order Executor)
职责：接收交易指令，完成挂单、监控、撤单的全生命周期管理，返回成交回执
"""

from core.logger import get_logger

logger = get_logger(__name__)

from typing import Dict, Optional
from dataclasses import dataclass, field
import pandas as pd


@dataclass
class PendingOrder:
    """挂单记录"""
    order_id: str
    symbol: str
    action: str          # 'BUY' or 'SELL'
    target_volume: int
    target_amount: float
    submitted_price: float
    priority: int
    status: str          # 'PENDING', 'FILLED', 'CANCELLED', 'EXPIRED'
    time_window: str


class OrderExecutor:
    """
    交易执行层
    管理订单提交、冻结/解冻、成交/撤单全流程
    """
    
    def __init__(self):
        self.pending_orders: Dict[str, PendingOrder] = {}
        self.order_counter = 0
        self.execution_reports: list = []
    
    def submit_order(self, order: dict, account, current_price: float, trade_date=None) -> Optional[str]:
        """
        提交订单 -> 立即冻结资产
        order: 来自 RiskManager 审批后的订单
        """
        symbol = order['symbol']
        action = order['action']
        volume = order['target_volume']
        amount = order.get('target_amount', volume * current_price)
        
        # ---------- 冻结资产 ----------
        if action == 'BUY':
            cost = volume * current_price
            # 检查可用资金是否充足
            if account.available_cash < cost:
                logger.error(f"❌ 资金不足: 需要 {cost:.2f}, 可用 {account.available_cash:.2f}")
                return None
            # 执行冻结
            account.cash -= cost
            account.frozen_cash += cost
        else:  # SELL
            # 检查可用持仓是否充足
            pos = account.positions.get(symbol)
            if not pos:
                logger.error(f"❌ 无持仓: {symbol}")
                return None
            available = pos.shares - pos.frozen_shares
            if available < volume:
                logger.error(f"❌ 可用持仓不足: 需要 {volume}, 可用 {available}")
                return None
            # 执行冻结
            pos.shares -= volume
            pos.frozen_shares += volume
        
        # ---------- 生成订单ID并记录 ----------
        order_id = f"ORD_{self.order_counter:06d}"
        self.order_counter += 1
        
        self.pending_orders[order_id] = PendingOrder(
            order_id=order_id,
            symbol=symbol,
            action=action,
            target_volume=volume,
            target_amount=amount,
            submitted_price=current_price,
            priority=order.get('priority', 5),
            status='PENDING',
            time_window=order.get('time_window', '09:30-14:50')
        )
        
        logger.info(f"📋 订单已提交: {order_id} {action} {symbol} {volume}股 @ {current_price:.2f}")
        return order_id
    
    def execute_order(self, order_id: str, account, fill_price: float, commission: float, trade_date=None) -> Optional[dict]:
        """
        成交回执 -> 执行交割，释放冻结标记
        """
        if order_id not in self.pending_orders:
            logger.error(f"❌ 订单不存在: {order_id}")
            return None
        
        pending = self.pending_orders.pop(order_id)
        symbol = pending.symbol
        volume = pending.target_volume
        action = pending.action
        
        if action == 'BUY':
            # 买入成交：解冻资金 + 更新持仓（移动加权平均）
            cost = volume * fill_price
            account.frozen_cash -= cost
            
            # 更新持仓
            pos = account.positions.get(symbol)
            if pos:
                # 移动加权平均
                total_shares = pos.shares + pos.frozen_shares + volume
                total_cost = pos.shares * pos.avg_cost + cost
                # 注意：此时 pos.shares 已经因为冻结减少，但我们用总持仓计算
                # 需要从冻结状态恢复：总持仓 = 原持仓 - 冻结 + 新买入
                # 更稳健的方式：直接从账簿读取原始持仓
                # 这里我们用简化方式：从冻结状态恢复
                pos.shares += volume  # 增加持仓（之前冻结时已减少）
                # 重新计算平均成本
                total_shares = pos.shares
                total_cost = pos.shares * pos.avg_cost + cost
                pos.avg_cost = total_cost / total_shares
            else:
                account.positions[symbol] = Position(shares=volume, avg_cost=fill_price)
            
            # 更新总资产
            account.total_asset = account.cash + sum(
                p.shares * fill_price for p in account.positions.values()
            )
            
        else:  # SELL
            # 卖出成交：解冻股票 + 增加现金
            proceed = volume * fill_price - commission
            account.frozen_cash -= 0  # 卖出不冻结现金，但之前冻结了股票
            
            # 恢复持仓（冻结时已减少，成交后不再恢复）
            pos = account.positions.get(symbol)
            if pos:
                pos.frozen_shares -= volume
                # 卖出后总持仓不变（因为冻结时已减少，成交后保持）
                # 但我们需要记录盈亏
                realized_pnl = (fill_price - pos.avg_cost) * volume
                logger.info(f"📊 卖出盈亏: {realized_pnl:.2f}")
            
            account.cash += proceed
            account.total_asset = account.cash + sum(
                p.shares * fill_price for p in account.positions.values()
            )
        
        # 生成成交回执
        report = {
            'order_id': order_id,
            'symbol': symbol,
            'action': action,
            'filled_volume': volume,
            'filled_amount': volume * fill_price,
            'commission': commission,
            'fill_price': fill_price,
            'timestamp': pd.Timestamp(trade_date) if trade_date else pd.Timestamp.now()
        }
        self.execution_reports.append(report)
        
        logger.info(f"✅ 成交: {order_id} {action} {symbol} {volume}股 @ {fill_price:.2f}")
        return report
    
    def cancel_order(self, order_id: str, account) -> bool:
        """
        撤单 -> 立即解冻资产
        """
        if order_id not in self.pending_orders:
            logger.error(f"❌ 订单不存在: {order_id}")
            return False
        
        pending = self.pending_orders.pop(order_id)
        symbol = pending.symbol
        volume = pending.target_volume
        action = pending.action
        amount = pending.target_amount
        
        if action == 'BUY':
            # 解冻资金
            account.frozen_cash -= amount
            account.cash += amount
        else:  # SELL
            # 解冻股票
            pos = account.positions.get(symbol)
            if pos:
                pos.frozen_shares -= volume
                pos.shares += volume
        
        pending.status = 'CANCELLED'
        logger.info(f"🗑️ 撤单: {order_id} {action} {symbol}")
        return True
    
    def expire_all_pending(self, account):
        """收盘强制清理：将所有挂单置为EXPIRED并解冻"""
        expired = []
        for order_id, pending in list(self.pending_orders.items()):
            # 强制解冻
            self.cancel_order(order_id, account)
            pending.status = 'EXPIRED'
            expired.append(order_id)
        return expired
    
    def get_reports_df(self) -> pd.DataFrame:
        """获取所有成交回执"""
        return pd.DataFrame(self.execution_reports)
