"""
电子云三层表建表脚本
"""

import sqlite3
from pathlib import Path

# 获取当前文件所在目录的父目录的父目录的 data/index_store/（真实库）
BASE_DIR = Path(__file__).parent.parent.parent
from config.config import PATTERN_DB_PATH as DB_PATH  # 统一路径（2026-08-26）


def create_electron_cloud_tables():
    """创建电子云三层表（索引表、分布表、聚合表）"""
    # 确保目录存在
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # 1. 索引表
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

    # 2. 分布表
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

    # 3. 聚合表
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

    # 建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cloud_index_pattern ON electron_cloud_index(pattern_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cloud_index_position ON electron_cloud_index(band_position)")

    conn.commit()
    conn.close()
    print(f"✅ 电子云三层表创建完成，数据库路径：{DB_PATH}")


if __name__ == "__main__":
    create_electron_cloud_tables()