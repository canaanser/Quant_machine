"""
资金风控处 (Risk Manager)
职责：接收策略信号，结合账户资产、预设风控规则及全局优先级，审批资金并生成交易指令
"""

from core.logger import get_logger

logger = get_logger(__name__)

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
    资金风控处（封控层，2026-08-28 老板定：全权负责买卖点增删减改）
    职责：拦不良买单/止损(机械+动态)/止盈/分批/保护期/死叉放行——策略只标记买卖点，筛选调节全在这
    """
    
    def __init__(self, config: dict, verbose: bool = False,
                 stop_loss_pct: float = None, take_profit_pct: float = None,
                 batch_exit: bool = False, protect_days: int = 0,
                 deadcross_low: float = -0.40, deadcross_strength: float = 0.15):
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
        # 铁律并入封控层（2026-08-28）：止损/止盈/分批/保护期全部封控层管
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct or (stop_loss_pct * 2 if stop_loss_pct else None)
        self.batch_exit = batch_exit
        self.protect_days = protect_days
        # 死叉真假判定参数（2026-08-29 实验可调）：低位阈值/强度阈值
        self.deadcross_low = deadcross_low
        self.deadcross_strength = deadcross_strength

    def evaluate_exits(self, positions: dict, prices: dict, today) -> List[dict]:
        """封控层止损/止盈评估（判定在此，执行由执行层 _sell）：
        机械止损=认错（企稳后抄底仍跌超止损线=抄错底，最高优先级全卖）；
        止盈=盈利垫子锁利（≥2×止损 卖一半）。
        positions: {symbol: {'shares','avg_cost','buy_source','buy_date'}}"""
        orders = []
        for symbol, pos in positions.items():
            price = prices.get(symbol)
            if not price or pos.get('avg_cost', 0) <= 0 or pos['shares'] <= 0:
                continue
            pnl = (price - pos['avg_cost']) / pos['avg_cost']
            # 机械止损（最高优先级，认错——不扛抄错的单）
            if self.stop_loss_pct and pnl <= -self.stop_loss_pct:
                orders.append({'symbol': symbol, 'action': 'SELL',
                               'target_volume': pos['shares'],
                               'reason': '机械止损(认错)', 'priority': 9})
                continue
            # 止盈（盈利垫子锁利，卖一半）
            if self.take_profit_pct and pnl >= self.take_profit_pct:
                half = (pos['shares'] // 2 // 100) * 100
                if half >= 100:
                    orders.append({'symbol': symbol, 'action': 'SELL',
                                   'target_volume': half,
                                   'reason': '止盈锁利', 'priority': 8})
        return orders

    def in_protection(self, pos: dict, today) -> bool:
        """保护期：人主动买入 protect_days 日内，策略信号不卖（止损/止盈照常）"""
        if not self.protect_days or pos.get('buy_source') != 'human':
            return False
        buy_date = pos.get('buy_date')
        if not buy_date:
            return False
        return (pd.Timestamp(today) - pd.Timestamp(buy_date)).days < self.protect_days

    def judge_deadcross_exit(self, pnl: float, pct_250d_high, strength: float) -> tuple:
        """死叉卖真假判定（2026-08-28 老板方案2：死叉可能是底背离/浮盈/小反转，真假由封控层判）
        返回 (应不应卖, 理由)：
          1. 有浮盈(pnl>0) → 不卖（盈利垫子交由止盈/动态止损管理）
          2. 疑似底背离（低位死叉：距250日高点<deadcross_low）→ 不卖（深跌低位死叉可能是反转）
          3. 弱死叉（strength<deadcross_strength）→ 不卖（小幅反转，卖了踏空）
          4. 真死叉 → 卖（分批由 batch_exit 决定）
        参数 deadcross_low/deadcross_strength 可实验调优。"""
        if pnl > 0:
            return False, '死叉时有浮盈→交由止盈管理'
        if pct_250d_high is not None and pct_250d_high < self.deadcross_low:
            return False, '疑似底背离(低位死叉)→不卖'
        if strength is not None and strength < self.deadcross_strength:
            return False, '弱死叉(小反转)→不卖'
        return True, '真死叉→执行卖出'

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
                    logger.debug(f"   🔴 触发妖股硬止损: {symbol}, 盈亏={pnl:.2%}")
                return self._gen_order(symbol, 'SELL', pos.shares, priority=9, reason='妖股硬止损')
            if signal.get('tag') == 'blue_chip' and pnl <= -self.stop_loss_gentle:
                if self.verbose:
                    logger.debug(f"   🔴 触发蓝筹软止损: {symbol}, 盈亏={pnl:.2%}")
                return self._gen_order(symbol, 'SELL', pos.shares, priority=4, reason='蓝筹软止损')
            if pnl >= self.profit_take:
                if self.verbose:
                    logger.debug(f"   🟢 触发止盈: {symbol}, 盈亏={pnl:.2%}")
                return self._gen_order(symbol, 'SELL', pos.shares, priority=3, reason='止盈')
        
        # ---------- Step 2: 买入审批 ----------
        if signal['action'] == 'BUY':
            raw_score = signal.get('score', 0)
            
            if abs(raw_score) < self.dead_zone:
                if self.verbose:
                    logger.debug(f"   ❌ 买入被拒: {symbol}, 评分={raw_score:.4f} 低于死区 {self.dead_zone}")
                return None
            
            if raw_score > 0:
                if current_price is None or pd.isna(current_price):
                    # 防御：NaN 价格（停牌/数据缺失）直接拒绝买入
                    if self.verbose:
                        logger.debug(f"   ❌ 买入被拒: {symbol}, 当前价格无效 (NaN)")
                    return None
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
                        logger.debug(f"   ❌ 买入被拒: {symbol}, 仓位已满")
                    return None
                
                target_amount = min(target_amount, remaining_slot)
                
                if target_amount > account.available_cash:
                    target_amount = account.available_cash
                    if self.verbose:
                        logger.debug(f"   ⚠️ 现金不足, 缩减至可用现金: {target_amount:.2f}")
                
                target_volume = int(target_amount / current_price / 100) * 100
                if target_volume < 100:
                    if self.verbose:
                        logger.debug(f"   ❌ 买入被拒: {symbol}, 目标股数={target_volume} 小于100股")
                    return None
                
                actual_amount = target_volume * current_price
                if actual_amount < self.min_order_amount:
                    if self.verbose:
                        logger.debug(f"   ❌ 买入被拒: {symbol}, 订单金额={actual_amount:.2f} 低于最小下单金额 {self.min_order_amount}")
                    return None
                
                if actual_amount > account.available_cash:
                    if self.verbose:
                        logger.debug(f"   ❌ 买入被拒: {symbol}, 现金不足")
                    return None
                
                priority = self._calc_priority(signal)
                if self.verbose:
                    logger.debug(f"   ✅ 买入审批通过: {symbol} {target_volume}股, 金额={actual_amount:.2f}, 评分={raw_score:.4f}")
                return self._gen_order(symbol, 'BUY', target_volume, priority, 
                                       target_amount=actual_amount, reason='策略买入')
            else:
                if self.verbose:
                    logger.debug(f"   ❌ 买入被拒: {symbol}, 评分为负 {raw_score:.4f}")
                return None
        
        # ---------- Step 3: 卖出审批 ----------
        if signal['action'] == 'SELL':
            pos = account.positions.get(symbol)
            if not pos or pos.shares <= 0:
                if self.verbose:
                    logger.debug(f"   ⚠️ 卖出失败: {symbol} 无持仓")
                return None
            
            available = pos.shares - pos.frozen_shares
            if available <= 0:
                if self.verbose:
                    logger.debug(f"   ⚠️ 卖出失败: {symbol} 可用持仓为0")
                return None
            
            sell_volume = available
            priority = 7
            if self.verbose:
                logger.debug(f"   ✅ 卖出审批通过: {symbol} {sell_volume}股, 优先级={priority}")
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