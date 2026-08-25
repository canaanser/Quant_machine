"""
结构感知层输出契约（StateTable）
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class StateTable:
    date: str
    symbol: str
    pattern_ids: List[str] = field(default_factory=list)
    pattern_type: str = ""
    category: str = "neutral"
    strength: float = 0.0
    vote_score: float = 0.0
    vote_pool_rank: Optional[int] = None
    data_quality: str = "valid"
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "symbol": self.symbol,
            "pattern_ids": self.pattern_ids,
            "pattern_type": self.pattern_type,
            "category": self.category,
            "strength": round(self.strength, 4),
            "vote_score": round(self.vote_score, 4),
            "vote_pool_rank": self.vote_pool_rank,
            "data_quality": self.data_quality,
            "meta": self.meta,
        }


@dataclass
class SignalTable:
    date: str
    symbol: str
    score: float
    confidence: float
    source: str = "structure_engine"

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "symbol": self.symbol,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "source": self.source,
        }


@dataclass
class OrderTable:
    symbol: str
    action: str
    target_volume: int
    target_amount: float
    price_limit: float
    priority: int = 5

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "target_volume": self.target_volume,
            "target_amount": round(self.target_amount, 2),
            "price_limit": round(self.price_limit, 2),
            "priority": self.priority,
        }


@dataclass
class ExecutionReport:
    order_id: str
    symbol: str
    action: str
    filled_volume: int
    filled_amount: float
    commission: float
    status: str

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "action": self.action,
            "filled_volume": self.filled_volume,
            "filled_amount": round(self.filled_amount, 2),
            "commission": round(self.commission, 2),
            "status": self.status,
        }
