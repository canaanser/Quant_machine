from .data_structures import metadata
from .data_loader import load_data
from .strategy import AlphaScoreStrategy
from .backtest import BacktestPipeline

__all__ = ['metadata', 'load_data', 'AlphaScoreStrategy', 'BacktestPipeline']


# ---------- 新增模块导出 ----------
from .risk_manager import RiskManager, Account, Position, create_default_account
from .order_executor import OrderExecutor
from .performance_analyzer import PerformanceAnalyzer
from .factor_modulator import FactorModulator
from .signal_modulator import SignalModulator

# ---------- 适配器模块导出 ----------
from .standard_structures import PositionInfo, AccountInfo
from .base_adapter import BrokerAdapter
from .simulated_adapter import SimulatedBrokerAdapter
