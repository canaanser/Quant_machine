# -*- coding: utf-8 -*-
"""
表结构定义与初始化（建表/加字段/索引）
（2026-08-26 小二陈：从 data_writer.py 拆出，接口不变）
"""
import sqlite3
from . import connection as _conn

def _init_tables():
    """初始化所有表（首次运行时自动创建），并兼容新增字段。
    性能优化：按 SCHEMA_VERSION 缓存，版本未变时跳过重复 DDL（原来每次写入都跑全套建表检查）。
    数据库文件被替换时，通过关键表存在性检查兜底重建。"""
    if _conn._initialized_version == _conn.SCHEMA_VERSION:
        # 版本未变：快速检查关键表是否仍在（防止库文件被替换后缺表）
        try:
            conn = _conn.get_global_connection()
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pattern_history'"
            ).fetchone()
            if row:
                return
        except Exception:
            pass
        # 关键表缺失 → 继续执行完整初始化
    conn = _conn.get_global_connection()
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
            open_price REAL,
            return_1d REAL, return_2d REAL, return_3d REAL, return_4d REAL, return_5d REAL,
            drawdown_from_peak REAL,
            days_since_peak INTEGER,
            cooldown_days INTEGER,
            return_10d REAL,
            return_20d REAL,
            composite_return REAL,
            signed_score REAL,
            base_score REAL,
            strength REAL,
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
        # V3 扩表（2026-08-27 老板确认）：逐日收益/开盘价/处境/冷却
        ("open_price", "REAL"),
        ("return_1d", "REAL"),
        ("return_2d", "REAL"),
        ("return_3d", "REAL"),
        ("return_4d", "REAL"),
        ("return_5d", "REAL"),
        ("drawdown_from_peak", "REAL"),
        ("days_since_peak", "INTEGER"),
        ("cooldown_days", "INTEGER"),
        # 回测读表改造（2026-08-28）：形态匹配强度（先验，供回测融合，无未来函数）
        ("strength", "REAL"),
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
    _conn._initialized_version = _conn.SCHEMA_VERSION  # 记录已初始化版本，后续写入跳过重复 DDL
