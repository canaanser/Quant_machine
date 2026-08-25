"""
数据写入器 - 形态历史记录表 + 原子特征记录表 + 扫描进度表 + 股票属性历史表
存储路径：data/index_store/pattern_history.db
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# ===== 数据库路径 =====
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "index_store" / "pattern_history.db"

# ===== 全局数据库连接（复用，避免锁冲突） =====
_global_conn = None


def _get_connection():
    """获取数据库连接，确保目录存在"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(DB_PATH))


def get_global_connection():
    """获取全局复用连接（所有写入操作共用）"""
    global _global_conn
    if _global_conn is None:
        _global_conn = _get_connection()
    return _global_conn


def close_global_connection():
    """关闭全局连接（在测试脚本末尾调用）"""
    global _global_conn
    if _global_conn:
        _global_conn.commit()
        _global_conn.close()
        _global_conn = None


def _init_tables():
    """初始化所有表（首次运行时自动创建），并兼容新增字段"""
    conn = get_global_connection()
    cursor = conn.cursor()

    # =============================================================
    # 1. 创建所有表（如果不存在）
    # =============================================================

    # 1.1 形态历史记录表（含波段位置字段 + pending 状态字段）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pattern_history (
            record_id TEXT PRIMARY KEY,
            symbol TEXT,
            pattern_id TEXT,
            pattern_name TEXT,
            category TEXT,
            match_date TEXT,
            match_price REAL,
            peak_date TEXT,
            valley_date TEXT,
            band_position TEXT,
            band_progress REAL,
            band_direction TEXT,
            wave_id TEXT,
            band_position_ready INTEGER DEFAULT 0,
            band_position_updated_at TEXT,
            return_5d REAL,
            return_10d REAL,
            return_20d REAL,
            composite_return REAL,
            signed_score REAL,
            base_score REAL,
            scan_version INTEGER,
            created_at TEXT
        )
    """)

    # 1.2 原子特征记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS atomic_features (
            record_id TEXT PRIMARY KEY,
            symbol TEXT,
            date TEXT,
            pattern_id TEXT,
            body_ratio REAL,
            shadow_ratio REAL,
            gap_ratio REAL,
            engulfing REAL,
            inside REAL,
            consecutive_bars REAL,
            volume_spike REAL,
            created_at TEXT
        )
    """)

    # 1.3 扫描进度表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scan_progress (
            symbol TEXT PRIMARY KEY,
            last_scanned_date TEXT,
            last_window_start TEXT,
            scan_mode TEXT,
            scan_version INTEGER,
            last_run TEXT
        )
    """)

    # 1.4 波段记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wave_history (
            wave_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            wave_type TEXT NOT NULL,
            start_date TEXT NOT NULL,
            start_price REAL NOT NULL,
            end_date TEXT NOT NULL,
            end_price REAL NOT NULL,
            total_return REAL NOT NULL,
            peak_date TEXT,
            peak_price REAL,
            valley_date TEXT,
            valley_price REAL,
            amplitude REAL,
            duration INTEGER,
            data_pointer TEXT,
            scan_version INTEGER,
            created_at TEXT
        )
    """)

    # 1.5 股票属性历史表（预建空表，V3.0 预留）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_attributes_history (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            sector TEXT,
            market_cap REAL,
            volatility_20d REAL,
            tags TEXT,
            pe_ttm REAL,
            pb_ttm REAL,
            PRIMARY KEY (symbol, date)
        )
    """)

    # 1.6 电子云索引表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS electron_cloud_index (
            grid_id TEXT PRIMARY KEY,
            pattern_id TEXT NOT NULL,
            band_position TEXT NOT NULL,
            sample_count INTEGER DEFAULT 0,
            confidence_level TEXT,
            distribution_id TEXT,
            last_updated TEXT,
            UNIQUE(pattern_id, band_position)
        )
    """)

    # 1.7 电子云分布表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS electron_cloud_distribution (
            distribution_id TEXT PRIMARY KEY,
            grid_id TEXT NOT NULL,
            sample_list TEXT,
            mean_return REAL,
            std_return REAL,
            positive_ratio REAL,
            min_return REAL,
            max_return REAL,
            sample_count INTEGER,
            created_at TEXT,
            FOREIGN KEY (grid_id) REFERENCES electron_cloud_index(grid_id)
        )
    """)

    # 1.8 电子云聚合表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS electron_cloud_aggregate (
            aggregate_id TEXT PRIMARY KEY,
            pattern_id TEXT NOT NULL,
            band_position TEXT NOT NULL,
            fit_function TEXT,
            params_json TEXT,
            fit_score REAL,
            sample_count INTEGER,
            version INTEGER,
            created_at TEXT,
            UNIQUE(pattern_id, band_position, version)
        )
    """)

    # =============================================================
    # 2. 兼容已有数据库：先添加缺失的字段（在索引之前）
    # =============================================================
    fields_to_add = [
        ("peak_date", "TEXT"),
        ("valley_date", "TEXT"),
        ("band_position", "TEXT"),
        ("band_progress", "REAL"),
        ("band_direction", "TEXT"),
        ("wave_id", "TEXT"),
        ("band_position_ready", "INTEGER DEFAULT 0"),
        ("band_position_updated_at", "TEXT"),
    ]
    for field_name, field_type in fields_to_add:
        try:
            cursor.execute(f"SELECT {field_name} FROM pattern_history LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(f"ALTER TABLE pattern_history ADD COLUMN {field_name} {field_type}")

    # =============================================================
    # 3. 建索引（此时所有字段都已存在）
    # =============================================================
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pattern_history_symbol ON pattern_history(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pattern_history_pattern_id ON pattern_history(pattern_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pattern_history_band_position ON pattern_history(band_position)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pattern_history_ready ON pattern_history(band_position_ready)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pattern_history_match_date ON pattern_history(match_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pattern_history_scan_version ON pattern_history(scan_version)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wave_history_symbol ON wave_history(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cloud_index_pattern ON electron_cloud_index(pattern_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cloud_index_position ON electron_cloud_index(band_position)")

    conn.commit()


def write_pattern_history(
    symbol: str,
    pattern_id: str,
    pattern_name: str,
    category: str,
    match_date: str,
    match_price: float,
    peak_date: Optional[str] = None,
    valley_date: Optional[str] = None,
    band_position: Optional[str] = None,
    band_progress: Optional[float] = None,
    band_direction: Optional[str] = None,
    wave_id: Optional[str] = None,
    band_position_ready: int = 0,
    band_position_updated_at: Optional[str] = None,
    return_5d: float = 0.0,
    return_10d: float = 0.0,
    return_20d: float = 0.0,
    composite_return: float = 0.0,
    signed_score: float = 0.0,
    base_score: float = 0.0,
    scan_version: int = 1
) -> str:
    """
    写入形态历史记录表
    返回 record_id
    """
    _init_tables()

    record_id = f"REC-{datetime.now().strftime('%Y%m%d')}-{symbol}-{uuid.uuid4().hex[:4]}"

    conn = get_global_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO pattern_history (
            record_id, symbol, pattern_id, pattern_name, category,
            match_date, match_price,
            peak_date, valley_date,
            band_position, band_progress, band_direction, wave_id,
            band_position_ready, band_position_updated_at,
            return_5d, return_10d, return_20d, composite_return,
            signed_score, base_score, scan_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record_id, symbol, pattern_id, pattern_name, category,
        match_date, match_price,
        peak_date, valley_date,
        band_position, band_progress, band_direction, wave_id,
        band_position_ready, band_position_updated_at,
        return_5d, return_10d, return_20d, composite_return,
        signed_score, base_score, scan_version, datetime.now().isoformat()
    ))

    conn.commit()
    return record_id


def write_atomic_features(
    symbol: str,
    date: str,
    pattern_id: str,
    atom_values: Dict[str, float]
) -> str:
    """
    写入原子特征记录表
    atom_values: 原子名 → 值的字典
    """
    _init_tables()

    record_id = f"ATOM-{datetime.now().strftime('%Y%m%d')}-{symbol}-{uuid.uuid4().hex[:4]}"

    conn = get_global_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO atomic_features (
            record_id, symbol, date, pattern_id,
            body_ratio, shadow_ratio, gap_ratio, engulfing,
            inside, consecutive_bars, volume_spike,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record_id, symbol, date, pattern_id,
        atom_values.get('BodyRatio', 0.0),
        atom_values.get('ShadowRatio', 0.0),
        atom_values.get('GapDetector', 0.0),
        atom_values.get('EngulfingDetector', 0.0),
        atom_values.get('InsideDetector', 0.0),
        atom_values.get('ConsecutiveBars', 0.0),
        atom_values.get('VolumeSpike', 0.0),
        datetime.now().isoformat()
    ))

    conn.commit()
    return record_id


def update_scan_progress(
    symbol: str,
    last_scanned_date: str,
    last_window_start: str,
    scan_mode: str = "incremental",
    scan_version: int = 1
):
    """更新扫描进度表"""
    _init_tables()

    conn = get_global_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO scan_progress (
            symbol, last_scanned_date, last_window_start, scan_mode, scan_version, last_run
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        symbol, last_scanned_date, last_window_start, scan_mode, scan_version,
        datetime.now().isoformat()
    ))

    conn.commit()


def get_last_scan_progress(symbol: str) -> Optional[Dict[str, Any]]:
    """获取指定股票的扫描进度"""
    _init_tables()

    conn = get_global_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM scan_progress WHERE symbol = ?
    """, (symbol,))

    row = cursor.fetchone()

    if row is None:
        return None

    columns = ['symbol', 'last_scanned_date', 'last_window_start', 'scan_mode', 'scan_version', 'last_run']
    return dict(zip(columns, row))


def get_pattern_history_count(symbol: Optional[str] = None) -> int:
    """获取形态历史记录总数（用于验证）"""
    _init_tables()

    conn = get_global_connection()
    cursor = conn.cursor()

    if symbol:
        cursor.execute("SELECT COUNT(*) FROM pattern_history WHERE symbol = ?", (symbol,))
    else:
        cursor.execute("SELECT COUNT(*) FROM pattern_history")

    count = cursor.fetchone()[0]
    return count


def get_pending_records_in_range(symbol: str, start_date: str, end_date: str) -> list:
    """
    获取指定波段范围内的 pending 记录（band_position_ready = 0）
    用于波段闭合后回填
    """
    _init_tables()

    conn = get_global_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT record_id, symbol, pattern_id, match_date, match_price, pattern_name, category
        FROM pattern_history
        WHERE symbol = ?
          AND match_date >= ? AND match_date <= ?
          AND band_position_ready = 0
    """, (symbol, start_date, end_date))

    rows = cursor.fetchall()
    return [
        {
            "record_id": row[0],
            "symbol": row[1],
            "pattern_id": row[2],
            "match_date": row[3],
            "match_price": row[4],
            "pattern_name": row[5],
            "category": row[6],
        }
        for row in rows
    ]


def update_band_position(
    record_id: str,
    band_position: str,
    band_progress: float,
    band_direction: str,
) -> int:
    """
    回填单条记录的 band_position，同时设置 band_position_ready = 1
    返回更新的记录数
    """
    _init_tables()

    conn = get_global_connection()
    cursor = conn.cursor()

    cursor.execute("""
            UPDATE pattern_history
            SET band_position = ?,
                band_progress = ?,
                band_direction = ?,
                band_position_ready = 1,
                band_position_updated_at = ?
            WHERE record_id = ?
    """, (
        band_position,
        band_progress,
        band_direction,
        datetime.now().isoformat(),
        record_id
    ))

    conn.commit()
    return cursor.rowcount

def write_wave_history(symbol: str, wave: dict, scan_version: int = 1) -> str:
    """写入波段记录表"""
    _init_tables()

    wave_id = f"WAVE-{datetime.now().strftime('%Y%m%d')}-{symbol}-{uuid.uuid4().hex[:4]}"

    conn = get_global_connection()
    cursor = conn.cursor()

    # 确定波段类型（上升/下降）
    if wave.get('direction') == 'up':
        wave_type = 'rise'
        start_date = wave.get('valley_date')
        start_price = wave.get('valley_price')
        end_date = wave.get('peak_date')
        end_price = wave.get('peak_price')
    else:
        wave_type = 'fall'
        start_date = wave.get('peak_date')
        start_price = wave.get('peak_price')
        end_date = wave.get('valley_date')
        end_price = wave.get('valley_price')

    # 计算波段总收益
    total_return = (end_price - start_price) / start_price if start_price != 0 else 0.0

    cursor.execute("""
        INSERT INTO wave_history (
            wave_id, symbol, wave_type, start_date, start_price, end_date, end_price,
            total_return, peak_date, peak_price, valley_date, valley_price, amplitude,
            duration, data_pointer, scan_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        wave_id,
        symbol,
        wave_type,
        start_date,
        start_price,
        end_date,
        end_price,
        total_return,
        wave.get('peak_date'),
        wave.get('peak_price'),
        wave.get('valley_date'),
        wave.get('valley_price'),
        wave.get('amplitude'),
        0,  # duration 暂不计算
        f"{symbol}_wave_{start_date}_{end_date}",
        scan_version,
        datetime.now().isoformat()
    ))

    conn.commit()
    return wave_id

