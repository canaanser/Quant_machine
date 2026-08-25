"""
资金风控处 (Risk Manager)
职责：接收策略信号，结合账户资产、预设风控规则及全局优先级，审批资金并生成交易指令
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
import pandas as pd


@dataclass
class Position:
    """单只股票的持仓信息"""
    shares: int = 0          # 总持仓（含冻结）
    frozen_shares: int = 0   # 卖出冻结部分
    avg_cost: float = 0.0    # 移动加权平均成本


@dataclass
class Account:
    """账户账簿"""
    cash: float = 0.0        # 总现金（含冻结）
    frozen_cash: float = 0.0 # 买入冻结部分
    positions: Dict[str, Position] = field(default_factory=dict)
    total_asset: float = 0.0 # 总资产（每日更新）
    
    @property
    def available_cash(self) -> float:
        """可用现金 = 总现金 - 冻结现金"""
        return self.cash - self.frozen_cash
    
    def available_shares(self, symbol: str) -> int:
        """可用持仓 = 总持仓 - 冻结持仓"""
        pos = self.positions.get(symbol)
        return pos.shares - pos.frozen_shares if pos else 0


class RiskManager:
    """
    资金风控处
    审批订单、执行止盈止损、控制仓位上限、计算优先级
    """
    
    def __init__(self, config: dict, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.max_pos_ratio = config.get('MAX_SINGLE_POSITION_RATIO', 0.80)
        self.stop_loss_aggressive = config.get('STOP_LOSS_AGGRESSIVE', 0.07)
        self.stop_loss_gentle = config.get('STOP_LOSS_GENTLE', 0.10)
        self.profit_take = config.get('PROFIT_TAKE_THRESHOLD', 0.30)
        self.base_position_ratio = config.get('BASE_POSITION_RATIO', 0.10)
        self.min_position_ratio = config.get('MIN_POSITION_RATIO', 0.01)
        self.min_order_amount = config.get('MIN_ORDER_AMOUNT', 100)
        self.dead_zone = config.get('DEAD_ZONE', 0.01)

    def approve_order(self, signal: dict, account: Account, current_price: float) -> Optional[dict]:
        """
        审批订单主流程
        """
        symbol = signal['symbol']
        pos = account.positions.get(symbol, Position())
        
        # ---------- Step 1: 强制止盈止损（最高优先级） ----------
        if pos.shares > 0:
            pnl = (current_price - pos.avg_cost) / pos.avg_cost
            
            if signal.get('tag') == 'high_volatility' and pnl <= -self.stop_loss_aggressive:
                if self.verbose:
                    print(f"   🔴 触发妖股硬止损: {symbol}, 盈亏={pnl:.2%}")
                return self._gen_order(symbol, 'SELL', pos.shares, priority=9, reason='妖股硬止损')
            if signal.get('tag') == 'blue_chip' and pnl <= -self.stop_loss_gentle:
                if self.verbose:
                    print(f"   🔴 触发蓝筹软止损: {symbol}, 盈亏={pnl:.2%}")
                return self._gen_order(symbol, 'SELL', pos.shares, priority=4, reason='蓝筹软止损')
            if pnl >= self.profit_take:
                if self.verbose:
                    print(f"   🟢 触发止盈: {symbol}, 盈亏={pnl:.2%}")
                return self._gen_order(symbol, 'SELL', pos.shares, priority=3, reason='止盈')
        
        # ---------- Step 2: 买入审批 ----------
        if signal['action'] == 'BUY':
            raw_score = signal.get('score', 0)
            
            if abs(raw_score) < self.dead_zone:
                if self.verbose:
                    print(f"   ❌ 买入被拒: {symbol}, 评分={raw_score:.4f} 低于死区 {self.dead_zone}")
                return None
            
            if raw_score > 0:
                effective_score = min(1.0, raw_score)
                min_ratio = self.min_position_ratio
                max_ratio = self.base_position_ratio
                effective_ratio = min_ratio + (max_ratio - min_ratio) * effective_score
                
                target_amount = account.total_asset * effective_ratio
                max_allowed = account.total_asset * self.max_pos_ratio
                current_value = pos.shares * current_price
                remaining_slot = max_allowed - current_value
                
                if remaining_slot <= 0:
                    if self.verbose:
                        print(f"   ❌ 买入被拒: {symbol}, 仓位已满")
                    return None
                
                target_amount = min(target_amount, remaining_slot)
                
                if target_amount > account.available_cash:
                    target_amount = account.available_cash
                    if self.verbose:
                        print(f"   ⚠️ 现金不足, 缩减至可用现金: {target_amount:.2f}")
                
                target_volume = int(target_amount / current_price / 100) * 100
                if target_volume < 100:
                    if self.verbose:
                        print(f"   ❌ 买入被拒: {symbol}, 目标股数={target_volume} 小于100股")
                    return None
                
                actual_amount = target_volume * current_price
                if actual_amount < self.min_order_amount:
                    if self.verbose:
                        print(f"   ❌ 买入被拒: {symbol}, 订单金额={actual_amount:.2f} 低于最小下单金额 {self.min_order_amount}")
                    return None
                
                if actual_amount > account.available_cash:
                    if self.verbose:
                        print(f"   ❌ 买入被拒: {symbol}, 现金不足")
                    return None
                
                priority = self._calc_priority(signal)
                if self.verbose:
                    print(f"   ✅ 买入审批通过: {symbol} {target_volume}股, 金额={actual_amount:.2f}, 评分={raw_score:.4f}")
                return self._gen_order(symbol, 'BUY', target_volume, priority, 
                                       target_amount=actual_amount, reason='策略买入')
            else:
                if self.verbose:
                    print(f"   ❌ 买入被拒: {symbol}, 评分为负 {raw_score:.4f}")
                return None
        
        # ---------- Step 3: 卖出审批 ----------
        if signal['action'] == 'SELL':
            pos = account.positions.get(symbol)
            if not pos or pos.shares <= 0:
                if self.verbose:
                    print(f"   ⚠️ 卖出失败: {symbol} 无持仓")
                return None
            
            available = pos.shares - pos.frozen_shares
            if available <= 0:
                if self.verbose:
                    print(f"   ⚠️ 卖出失败: {symbol} 可用持仓为0")
                return None
            
            sell_volume = available
            priority = 7
            if self.verbose:
                print(f"   ✅ 卖出审批通过: {symbol} {sell_volume}股, 优先级={priority}")
            return self._gen_order(symbol, 'SELL', sell_volume, priority, 
                                   target_amount=sell_volume * current_price, reason='死叉卖出')
        
        return None

    def _gen_order(self, symbol: str, action: str, volume: int, priority: int, 
                   target_amount: float = None, reason: str = "") -> dict:
        return {
            'symbol': symbol,
            'action': action,
            'target_volume': volume,
            'target_amount': target_amount or 0.0,
            'priority': priority,
            'price_limit': None,
            'time_window': "09:30-14:50",
            'reason': reason
        }

    def _calc_priority(self, signal: dict) -> int:
        score = signal.get('score', 0.5) * 5.0
        tag_bonus = 2.0 if signal.get('tag') == 'high_volatility' else 0.0
        total = score + tag_bonus
        return min(10, max(0, int(round(total))))


def create_default_account(initial_cash: float = 500000.0) -> Account:
    return Account(
        cash=initial_cash,
        frozen_cash=0.0,
        positions={},
        total_asset=initial_cash
    )