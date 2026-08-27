"""
全局配置（原有 + 新增结构感知层参数 + 趋势策略参数 + 权重更新参数）
"""

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

# ===== 扫描股票池（2026-08-27 老板扩充：原20通信 + 新增64 = 84只） =====
SCAN_TICKERS = [
    # 原20只通信池
    '000063', '600498', '002396', '600941', '601728', '600050',
    '300308', '300502', '300394', '002281', '300570', '300620', '688205',
    '600487', '600522', '601869', '603606', '002792', '000977', '002465',
    # 新增64只
    '000566', '000657', '000766', '000848', '000858', '000930', '000938',
    '001257', '002131', '002151', '002156', '002174', '002300', '002309',
    '002378', '002428', '002432', '002436', '002475', '002498', '002624',
    '002639', '002735', '002739', '002842', '002918', '002931', '002991',
    '300013', '300059', '300285', '300293', '300476',
    '301312', '301379', '301421',
    '600010', '600096', '600176', '600339', '600396', '600419', '600594',
    '600702', '600757', '600800', '600875', '600900', '600988',
    '601118', '601188', '601577', '601600', '601611', '601666',
    '601766', '601800', '601899',
    '603123', '603551', '603589', '603993',
    '688256', '688271',
]

# ===== AI 算力链龙头池（2026-08-28 小二陈，老板确认 20 只） =====# 英伟达财报 + 工信部算力/6G 政策双逻辑：PCB/铜缆/液冷/6G/国产算力/存储/服务器/光模块
SCAN_TICKERS_AI = [
    # 新加（不在主池）14 只
    '002463',   # 沪电股份 PCB
    '300476',   # 胜宏科技 PCB
    '002130',   # 沃尔核材 高速铜缆
    '002837',   # 英维克 液冷
    '301018',   # 申菱环境 液冷
    '688387',   # 信科移动 6G
    '688041',   # 海光信息 国产算力
    '603986',   # 兆易创新 存储
    '300475',   # 香农芯创 HBM
    '688008',   # 澜起科技 内存接口
    '601138',   # 工业富联 AI服务器
    '603019',   # 中科曙光 算力
    '002371',   # 北方华创 半导体设备
    '688012',   # 中微公司 半导体设备
    # 主池已有 6 只（幂等更新）
    '000063',   # 中兴通讯 6G/光通信
    '688256',   # 寒武纪 国产算力
    '000977',   # 浪潮信息 AI服务器
    '300308',   # 中际旭创 光模块
    '300502',   # 新易盛 光模块
    '600498',   # 烽火通信 光通信
]

# ===== 指数池（2026-08-28 小二陈）=====
# ⚠️ 探测确认：stockdb 是纯股票库（5821只），【未收录任何指数】！
# 000016/000688/000852/000905 都是股票（深康佳A/国城矿业/石化机械/厦门港务），非指数。
# 大盘基准改用：akshare 拉真实指数（见日程#4）或池内等权代理。此池已废弃。
SCAN_TICKERS_INDEX = []

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
    'WEIGHT_SOURCE', 'SCAN_TICKERS', 'SCAN_TICKERS_AI', 'SCAN_TICKERS_INDEX', 'PATTERN_DB_PATH',
    'get_data_path', 'ensure_dirs',
]