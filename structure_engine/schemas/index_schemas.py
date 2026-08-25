"""
索引表 + 查询结构定义
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class IndexRecord:
    index_id: str
    symbol: str
    start_date: str
    end_date: str
    segment_type: str
    features: Dict[str, Any]
    tags: List[str] = field(default_factory=list)
    best_buy: Dict[str, Any] = field(default_factory=dict)
    best_sell: Dict[str, Any] = field(default_factory=dict)
    ma_buy: Dict[str, Any] = field(default_factory=dict)
    ma_sell: Dict[str, Any] = field(default_factory=dict)
    data_pointer: Dict[str, Any] = field(default_factory=dict)
    forward_stats: Dict[str, float] = field(default_factory=dict)
    amplitude: float = 0.0
    duration: int = 0

    def to_dict(self) -> dict:
        return {
            "index_id": self.index_id,
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "segment_type": self.segment_type,
            "features": self.features,
            "tags": self.tags,
            "best_buy": self.best_buy,
            "best_sell": self.best_sell,
            "ma_buy": self.ma_buy,
            "ma_sell": self.ma_sell,
            "data_pointer": self.data_pointer,
            "forward_stats": self.forward_stats,
            "amplitude": round(self.amplitude, 4),
            "duration": self.duration,
        }


@dataclass
class QueryRequest:
    query_id: str
    symbol: Optional[str] = None
    lookback_days: int = 30
    features: Dict[str, Any] = field(default_factory=dict)
    match_tolerance: float = 0.15
    top_k: int = 10

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "symbol": self.symbol,
            "lookback_days": self.lookback_days,
            "features": self.features,
            "match_tolerance": self.match_tolerance,
            "top_k": self.top_k,
        }


@dataclass
class QueryResult:
    query_id: str
    matches: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "matches": self.matches,
        }
