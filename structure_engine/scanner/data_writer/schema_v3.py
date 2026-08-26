# -*- coding: utf-8 -*-
"""
新库表结构定义 V3.0（2026-08-27 小二陈）
=============================================
设计依据（本会话全部验证结论）：
1. 位置是主因子，但后验不可用 → 用先验处境（回撤/天数）替代
2. 5/10/20 日复合收益稀释短期信号 → 加 return_1d~5d 逐日收益
3. 形态有冷却期（不死鸟周期）→ 冷却≥60天信号最强 → 存 cooldown 字段
4. 首现/重生效应 → 存 prev_outcome（上次失效位置）
5. 红绿十字星疑似个股特异 → 存 candle_color
6. 趋势线/布林带是处境特征 → 预建节点表/状态表（一次扫全）

原则：一张大表 + symbol 索引（跨股票聚合是核心操作）；
      只加不删（旧字段保留兼容）；全部先验可算。
"""

# =============================================================
# 1. 形态历史表（大表，核心）
# =============================================================
CREATE_PATTERN_HISTORY = """
CREATE TABLE IF NOT EXISTS pattern_history (
    -- ===== 主键/标识 =====
    record_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,                -- 股票代码
    pattern_id TEXT NOT NULL,            -- 形态ID
    pattern_name TEXT,                   -- 形态名
    category TEXT,                       -- bullish/bearish/neutral

    -- ===== 匹配信息 =====
    match_date TEXT NOT NULL,            -- 形态出现日
    match_price REAL,                    -- 匹配日收盘价
    candle_color TEXT,                   -- 红/绿（close vs open，新增）
    candle_body REAL,                    -- 实体占比（新增，从原子冗余便于查询）

    -- ===== 波段位置（后验，复盘用） =====
    peak_date TEXT, valley_date TEXT,
    band_position TEXT, band_progress REAL, band_direction TEXT,
    wave_id TEXT,
    band_position_ready INTEGER DEFAULT 0,
    band_position_updated_at TEXT,

    -- ===== 先验处境（实盘可算，新增） =====
    drawdown_from_peak REAL,             -- 近120日高点回撤深度
    days_since_peak INTEGER,             -- 距近120日高点天数
    cooldown_days INTEGER,               -- 距该股该形态上次出现天数（冷却期）
    prev_outcome TEXT,                   -- 上次出现后5日走向: 'win'/'loss'/'first'（不死鸟周期）
    occurrence_rank INTEGER,             -- 该股该形态第几次出现（首现=1）

    -- ===== 逐日收益（新增，5列替代复合） =====
    -- 口径（2026-08-27 老板确认）：存【累计收益】而非每日收益率
    --   return_1d = close[+1]/close[0]-1  （第1天相对匹配日的累计）
    --   return_5d = close[+5]/close[0]-1  （第5天相对匹配日的累计）
    -- 理由：累计的相邻差值 = 每日收益率（return_2d-return_1d=第2天日收益），
    --       存累计可反推每日，存每日反而推不出累计（信息最全的选择）
    return_1d REAL, return_2d REAL, return_3d REAL, return_4d REAL, return_5d REAL,

    -- ===== 旧评分（保留兼容，新评分另立） =====
    return_5d_old REAL, return_10d REAL, return_20d REAL,
    composite_return REAL, signed_score REAL, base_score REAL,

    scan_version INTEGER,
    created_at TEXT
)
"""

# =============================================================
# 2. 趋势线节点表（新增，老板需求：一次扫全）
#    记录显著峰/谷（swing points）——上影线簇的"外包点"
#    设计依据（深造开源实现后定稿）：
#    - leoi137: 150日对数波动率×3σ 定阈值（自适应），序列截断保证
#      high→low 交替出现
#    - pytrendline: 影线簇归并（长上影包短上影，短影线不录）、
#      触碰计数≥3 才有效（查询时算）
#    - 锚点 append-only：只追加，趋势线查询时动态拟合，永不过期
# =============================================================
CREATE_TRENDLINE_NODES = """
CREATE TABLE IF NOT EXISTS trendline_nodes (
    node_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    node_date TEXT NOT NULL,
    node_price REAL NOT NULL,
    node_type TEXT NOT NULL,             -- 'peak' / 'valley'
    significance REAL,                   -- 显著性 = (节点价-邻域均值)/波动率倍数
                                         --   （相对值，跨股票可比；3σ 过滤后均显著）
    shadow_exceed REAL,                  -- 影线超出相邻K线比例（长影线外包程度）
    cluster_size INTEGER,                -- 归并的影线簇K线数（长影包住几条短影）
    wave_id TEXT,                        -- 关联波段（可选，无关联可空=单纯插入）
    related_pattern_id TEXT,             -- 触发该节点的形态（可选）
    scan_version INTEGER,
    created_at TEXT,
    UNIQUE(symbol, node_date, node_type)
)
"""

# =============================================================
# 3. 布林带状态表（新增，老板需求：一次扫全）
#    逐日状态，作为处境特征
# =============================================================
CREATE_BOLLINGER_STATES = """
CREATE TABLE IF NOT EXISTS bollinger_states (
    symbol TEXT NOT NULL,
    bdate TEXT NOT NULL,
    middle REAL, upper REAL, lower REAL,
    bandwidth REAL,                      -- (上-下)/中
    position REAL,                       -- 价格在通道位置 0~1
    upper_break INTEGER DEFAULT 0,       -- 触及/击穿上轨
    lower_break INTEGER DEFAULT 0,       -- 触及/击穿下轨
    squeeze INTEGER DEFAULT 0,           -- 挤压状态（带宽<历史20%分位）
    scan_version INTEGER,
    PRIMARY KEY (symbol, bdate)
)
"""

# =============================================================
# 4. 原子特征表（保留）
# =============================================================
CREATE_ATOMIC_FEATURES = """
CREATE TABLE IF NOT EXISTS atomic_features (
    record_id TEXT PRIMARY KEY,
    symbol TEXT, date TEXT, pattern_id TEXT,
    body_ratio REAL, shadow_ratio REAL, gap_ratio REAL,
    engulfing REAL, inside REAL, consecutive_bars REAL, volume_spike REAL,
    created_at TEXT
)
"""

# =============================================================
# 5. 波段表（保留）
# =============================================================
CREATE_WAVE_HISTORY = """
CREATE TABLE IF NOT EXISTS wave_history (
    wave_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL, wave_type TEXT NOT NULL,
    start_date TEXT NOT NULL, start_price REAL NOT NULL,
    end_date TEXT NOT NULL, end_price REAL NOT NULL,
    total_return REAL NOT NULL,
    peak_date TEXT, peak_price REAL,
    valley_date TEXT, valley_price REAL,
    amplitude REAL, duration INTEGER,
    data_pointer TEXT, scan_version INTEGER, created_at TEXT
)
"""

# =============================================================
# 6. 扫描进度表（保留）
# =============================================================
CREATE_SCAN_PROGRESS = """
CREATE TABLE IF NOT EXISTS scan_progress (
    symbol TEXT PRIMARY KEY,
    last_scanned_date TEXT, last_window_start TEXT,
    scan_mode TEXT, scan_version INTEGER, last_run TEXT
)
"""

# =============================================================
# 7. 索引
# =============================================================
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ph_symbol ON pattern_history(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_ph_symbol_date ON pattern_history(symbol, match_date)",
    "CREATE INDEX IF NOT EXISTS idx_ph_pattern ON pattern_history(pattern_id)",
    "CREATE INDEX IF NOT EXISTS idx_ph_band ON pattern_history(band_position)",
    "CREATE INDEX IF NOT EXISTS idx_tl_symbol ON trendline_nodes(symbol, node_date)",
    "CREATE INDEX IF NOT EXISTS idx_bs_symbol ON bollinger_states(symbol, bdate)",
    "CREATE INDEX IF NOT EXISTS idx_wave_symbol ON wave_history(symbol)",
]

ALL_CREATES = [
    CREATE_PATTERN_HISTORY,
    CREATE_TRENDLINE_NODES,
    CREATE_BOLLINGER_STATES,
    CREATE_ATOMIC_FEATURES,
    CREATE_WAVE_HISTORY,
    CREATE_SCAN_PROGRESS,
]
