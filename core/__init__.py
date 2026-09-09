from .struct.data_structures import metadata
from .data_loader import load_data
from .strategy import AlphaScoreStrategy
from .backtest import BacktestPipeline

__all__ = ['metadata', 'load_data', 'AlphaScoreStrategy', 'BacktestPipeline']


# ---------- 新增模块导出 ----------
from .backtest.risk_manager import RiskManager, Account, Position, create_default_account
from .backtest.order_executor import OrderExecutor
from .backtest.performance_analyzer import PerformanceAnalyzer
from .strategy.factor_modulator import FactorModulator
from .strategy.signal_modulator import SignalModulator

# ---------- 适配器模块导出 ----------
from .struct.standard_structures import PositionInfo, AccountInfo
from .trade.base_adapter import BrokerAdapter
from .backtest.simulated_adapter import SimulatedBrokerAdapter
from .trade.file_order_broker import FileOrderBroker

# ---------- 选池/筛选器模块导出（2026-08-30 小二陈：selection 在根目录） ----------
from selection import BaseSelector, WangwenSelector

# ---------- 标签系统导出（2026-08-30 老板：标签归类系统） ----------
from .stocktags import (BaseTagGenerator, register, unregister, get, list_tags,
                   load, produce, backfill, tag_at, filter,
                   assemble, hierarchy)

# ---------- 档案系统导出（2026-08-30 老板：股票=人，数据=档案） ----------
from .profile import StockProfile, assemble as assemble_profile, assemble_one
