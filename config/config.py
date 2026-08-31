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

# ===== 扩池（2026-08-28 老板拍板：沪深300+中证500 指数成分按权重选 78 只） =====
# v1（行业板块法）失败：银行/钢铁/医药小盘股 2017/2024 微盘崩盘致回撤 -79%；
# v2（指数成分法）根治：权重=市值代理，大中盘龙头，避开微盘/题材小盘
SCAN_TICKERS_EXT = [
    '601868', '003816', '600016', '601238', '600066', '002142', '601018', '300750',
    '603369', '601228', '600015', '688520', '600438', '600660', '688187', '002050',
    '688709', '600803', '600000', '601901', '600482', '601127', '002558', '688425',
    '601916', '601888', '600460', '300759', '601059', '603650', '000651', '600585',
    '300115', '600023', '000617', '300058', '601336', '300628', '600989', '688318',
    '605589', '002384', '600256', '002460', '000776', '603296', '600018', '600893',
    '601319', '603290', '600004', '600039', '600008', '002594', '600549', '603766',
    '600489', '600483', '600332', '601990', '600655', '688111', '603737', '600126',
    '000988', '600036', '601186', '300024', '002074', '600570', '600516', '601236',
    '603345', '688475', '601058', '600426', '603298', '000021',
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
# ===== 财报信息存储路径（2026-08-30 小二陈：Information 层，与回测 Data 区分） =====
# daily/   = 每日估值快照（原 data/fundamentals/，T 日实时 pe_ttm/pb/市值/股本/ST）
# reports/ = 定期财报期表（原 data/fundamentals_online/，5表JSON，含 pubDate/statDate）
FUNDAMENTALS_DAILY_DIR = "data/info/fundamentals/daily"      # 每日估值快照
FUNDAMENTALS_REPORTS_DIR = "data/info/fundamentals/reports"  # 定期财报期表

# ===== 标签系统路径（2026-08-30 老板：标签归类系统） =====
# data/info/tags/      标签数据（独立存储，可回填/可组装）
#   labels.json        标签池注册表（目录）
#   data/              标签长表（每生成器一文件：{name}_{version}.csv）
#   assembly/          组装结果缓存（可选）
TAGS_DIR = "data/info/tags"
TAGS_DATA_DIR = "data/info/tags/data"
TAGS_LABELS_PATH = "data/info/tags/labels.json"
TAGS_ASSEMBLY_DIR = "data/info/tags/assembly"


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
        FUNDAMENTALS_DAILY_DIR,
        FUNDAMENTALS_REPORTS_DIR,
        TAGS_DIR,
        TAGS_DATA_DIR,
        TAGS_ASSEMBLY_DIR,
    ]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)


# ===== 精选池（2026-08-28 老板"精挑细选"：质量信号最集中的 15 只） =====
# 从 84 只池按"深跌+放量信号数≥10 且 10日胜率≥65%"精选；
# 回测 1216.66%/Sharpe0.77（满仓），建仓档 254%/-29%——实盘候选池
SCAN_TICKERS_CURATED = [
    '002156',  # 通富微电 12信号/91.7%
    '002428',  # 云南锗业 11/81.8%
    '002281',  # 光迅科技 10/80.0%
    '002735',  # 王子新材 13/76.9%
    '600522',  # 中天科技 13/76.9%
    '300293',  # 蓝英装备 12/75.0%
    '300620',  # 光库科技 12/75.0%
    '600702',  # 舍得酒业 15/73.3%
    '600487',  # 亨通光电 14/71.4%
    '002309',  # 中利集团 24/70.8%
    '000566',  # 海南海药 10/70.0%
    '300502',  # 新易盛 22/68.2%
    '002792',  # 通宇通讯 15/66.7%
    '300570',  # 太辰光 17/64.7%
    '002918',  # 蒙娜丽莎 19/63.2%
]


# ===== 选池筛选器配置（2026-08-30 小二陈） =====
# 王文五标准绝对阈值（与 selection/wangwen.py 一致，单一事实源）
WANGWEN_PE_MAX = 30.0      # ① 低估值：pe < 30
WANGWEN_PB_MAX = 5.0       # ① 低估值：pb < 5
WANGWEN_OCF_MIN = 0.5      # ② 高现金流：经营现金流/营业利润 > 0.5
WANGWEN_GROSS_MIN = 20.0   # ④ 业务可持续：毛利率 > 20%
WANGWEN_NET_MIN = 0.0      # ④ 业务可持续：净利率 > 0
WANGWEN_REV_YOY_MIN = 0.0  # ⑤ 有梦想：营收同比 > 0
WANGWEN_NP_YOY_MIN = 0.0   # ⑤ 有梦想：净利同比 > 0


# ===== 导出清单（供 config/__init__.py 转发，单一事实源） =====
__all__ = [
    'START_DATE', 'END_DATE', 'INITIAL_CASH', 'COMMISSION', 'TOP_N', 'WINDOW', 'LOOKBACK',
    'SCAN_WINDOW', 'MIN_AMPLITUDE', 'PEAK_VALLEY_LOOKBACK',
    'INDEX_STORE_PATH', 'INDEX_SIMILARITY_TOLERANCE', 'INDEX_TOP_K', 'INDEX_AUTO_REBUILD',
    'FEATURE_KLINE_DIM', 'FEATURE_MA_DIM',
    'VOTE_POOL_PATH', 'VOTE_DORMANCY_THRESHOLD', 'VOTE_MIN_OCCURRENCES', 'VOTE_CHECK_INTERVAL',
    'TREND_STRATEGY_WEIGHTS', 'TREND_THRESHOLD', 'TREND_CURVE_POWER',
    'PATTERN_WEIGHT_LEARNING_RATE', 'PATTERN_MIN_SAMPLES',
    'WEIGHT_SOURCE', 'SCAN_TICKERS', 'SCAN_TICKERS_AI', 'SCAN_TICKERS_EXT', 'SCAN_TICKERS_CURATED',
    'SCAN_TICKERS_INDEX', 'PATTERN_DB_PATH', 'PROJECT_ROOT',
    'FUNDAMENTALS_DAILY_DIR', 'FUNDAMENTALS_REPORTS_DIR',
    'TAGS_DIR', 'TAGS_DATA_DIR', 'TAGS_LABELS_PATH', 'TAGS_ASSEMBLY_DIR',
    'WANGWEN_PE_MAX', 'WANGWEN_PB_MAX', 'WANGWEN_OCF_MIN',
    'WANGWEN_GROSS_MIN', 'WANGWEN_NET_MIN', 'WANGWEN_REV_YOY_MIN', 'WANGWEN_NP_YOY_MIN',
    'get_data_path', 'ensure_dirs',
]