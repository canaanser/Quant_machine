"""
全局配置（原有 + 新增结构感知层参数 + 趋势策略参数 + 权重更新参数）
"""

import os
from pathlib import Path

# ===== 原有配置 =====
START_DATE = "2025-01-01"
END_DATE = "2026-07-31"
INITIAL_CASH = 500000
COMMISSION = 0.00012
TOP_N = 10
WINDOW = 60
LOOKBACK = 20

# ===== 结构感知层参数（新增） =====
SCAN_WINDOW = 150                     # 扫描窗口（交易日）
MIN_AMPLITUDE = 0.08                  # 有效波段最小振幅（8%）
PEAK_VALLEY_LOOKBACK = 5              # 波峰/波谷确认窗口（左右各N日）

# ===== 索引引擎参数（新增） =====
INDEX_STORE_PATH = "data/index_store/index.db"     # SQLite索引库路径
INDEX_SIMILARITY_TOLERANCE = 0.15                  # 相似度容差
INDEX_TOP_K = 10                                   # 查询返回数量
INDEX_AUTO_REBUILD = False                         # 规则变更时自动重建

# ===== 特征提取参数（新增） =====
FEATURE_KLINE_DIM = 8                 # K线形状特征维度
FEATURE_MA_DIM = 4                    # 均线位置特征维度

# ===== 投票池参数（新增） =====
VOTE_POOL_PATH = "data/index_store/vote_pool.db"
VOTE_DORMANCY_THRESHOLD = 0.3         # 休眠阈值倍数（中位数×0.3）
VOTE_MIN_OCCURRENCES = 5              # 休眠所需的最少出现次数
VOTE_CHECK_INTERVAL = 7               # 沉底检查间隔（天）

# ===== 趋势强度策略参数（新增） =====
TREND_STRATEGY_WEIGHTS = {
    'position_weight': 0.4,      # 均线偏离度权重
    'momentum_weight': 0.4,      # MACD动量权重
    'acceleration_weight': 0.2,  # MACD加速度权重
}
TREND_THRESHOLD = 0.25           # 清仓阈值（低于此值清仓）
TREND_CURVE_POWER = 1.5          # 仓位映射曲线幂次

# ===== 权重更新参数（新增） =====
PATTERN_WEIGHT_LEARNING_RATE = 0.1   # 权重更新学习率
PATTERN_MIN_SAMPLES = 5              # 最小样本量阈值（低于此值不参与更新）

# ===== 辅助函数 =====
def get_data_path(subdir: str = "") -> Path:
    """获取数据目录路径"""
    base = Path("data")
    if subdir:
        return base / subdir
    return base

def ensure_dirs():
    """确保所有数据目录存在"""
    dirs = [
        "data/index_store",
        "data/user_data",
        "outputs/backtest_results/performance",
    ]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)