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

# ===== 信号权重来源开关（2026-08-26 小二陈） =====
# 'legacy' = 现有 WEIGHT_MAP（经验设定）；'data' = 数据驱动权重表（贝叶斯收缩）
# 2026-08-26 经三轮复验（震荡市/暴涨市）数据权重全面占优，切换为 data（可随时回退 legacy）
WEIGHT_SOURCE = 'data'

# ===== 扫描股票池（第五步：多股票铺开，2026-08-26 小二陈） =====
# 通信板块及其产业链 20 只：设备 / 运营商 / 光模块 / 光器件 / 光纤光缆 / 海缆 / 算力
SCAN_TICKERS = [
    # 通信设备
    '000063', '600498', '002396',      # 中兴通讯、烽火通信、星网锐捷
    # 运营商
    '600941', '601728', '600050',      # 中国移动、中国电信、中国联通
    # 光模块
    '300308', '300502', '300394', '002281',  # 中际旭创、新易盛、天孚通信、光迅科技
    # 光器件
    '300570', '300620', '688205',      # 太辰光、光库科技、德科立
    # 光纤光缆
    '600487', '600522', '601869',      # 亨通光电、中天科技、长飞光纤
    # 海缆
    '603606',                          # 东方电缆
    # 天线
    '002792',                          # 通宇通讯
    # 算力 / 军工通信
    '000977', '002465',                # 浪潮信息、海格通信
]

# ===== 数据库路径统一（2026-08-26 小二陈） =====
# 消除多处重复定义（data_writer/electron_cloud_query/weight_estimator/signal_weights 各写一份）
PROJECT_ROOT = Path(__file__).parent.parent
PATTERN_DB_PATH = PROJECT_ROOT / "data" / "index_store" / "pattern_history.db"

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


# ===== 导出清单（供 config/__init__.py 转发，单一事实源） =====
__all__ = [
    'START_DATE', 'END_DATE', 'INITIAL_CASH', 'COMMISSION', 'TOP_N', 'WINDOW', 'LOOKBACK',
    'SCAN_WINDOW', 'MIN_AMPLITUDE', 'PEAK_VALLEY_LOOKBACK',
    'INDEX_STORE_PATH', 'INDEX_SIMILARITY_TOLERANCE', 'INDEX_TOP_K', 'INDEX_AUTO_REBUILD',
    'FEATURE_KLINE_DIM', 'FEATURE_MA_DIM',
    'VOTE_POOL_PATH', 'VOTE_DORMANCY_THRESHOLD', 'VOTE_MIN_OCCURRENCES', 'VOTE_CHECK_INTERVAL',
    'TREND_STRATEGY_WEIGHTS', 'TREND_THRESHOLD', 'TREND_CURVE_POWER',
    'PATTERN_WEIGHT_LEARNING_RATE', 'PATTERN_MIN_SAMPLES',
    'WEIGHT_SOURCE', 'SCAN_TICKERS', 'PATTERN_DB_PATH',
    'get_data_path', 'ensure_dirs',
]