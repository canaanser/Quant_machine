"""
向电子云分布表插入10条样本数据，验证三层表链路
"""

import sqlite3
import json
import uuid
from pathlib import Path
from datetime import datetime

from config.config import PATTERN_DB_PATH as DB_PATH  # 统一路径（2026-08-26）


def get_connection():
    return sqlite3.connect(str(DB_PATH))


def ensure_grid_id(pattern_id: str, band_position: str):
    """确保索引表中有对应的 grid_id，返回 grid_id"""
    conn = get_connection()
    cursor = conn.cursor()

    grid_id = f"{pattern_id}_{band_position}"

    cursor.execute("""
        INSERT OR IGNORE INTO electron_cloud_index (grid_id, pattern_id, band_position, sample_count, confidence_level, last_updated)
        VALUES (?, ?, ?, 0, NULL, ?)
    """, (grid_id, pattern_id, band_position, datetime.now().isoformat()))

    conn.commit()
    conn.close()
    return grid_id


def insert_sample(pattern_id: str, band_position: str, return_value: float):
    """插入一条样本到分布表，并更新索引表"""
    grid_id = ensure_grid_id(pattern_id, band_position)

    conn = get_connection()
    cursor = conn.cursor()

    # 1. 生成 distribution_id
    dist_id = f"DIST-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"

    # 2. 查询该 grid_id 当前的样本列表
    cursor.execute("""
        SELECT sample_list, sample_count, mean_return FROM electron_cloud_distribution
        WHERE grid_id = ?
        ORDER BY created_at DESC LIMIT 1
    """, (grid_id,))
    row = cursor.fetchone()

    if row:
        sample_list = json.loads(row[0])
        sample_list.append(return_value)
        old_count = row[1]
        old_mean = row[2]
        new_count = old_count + 1
        new_mean = old_mean + (return_value - old_mean) / new_count
    else:
        sample_list = [return_value]
        new_count = 1
        new_mean = return_value

    # 3. 计算统计量
    import math
    mean = new_mean
    variance = sum((x - mean) ** 2 for x in sample_list) / len(sample_list)
    std = math.sqrt(variance) if variance > 0 else 0.0
    positive_ratio = sum(1 for x in sample_list if x > 0) / len(sample_list)
    min_val = min(sample_list)
    max_val = max(sample_list)

    # 4. 插入分布表
    cursor.execute("""
        INSERT INTO electron_cloud_distribution (
            distribution_id, grid_id, sample_list, mean_return, std_return,
            positive_ratio, min_return, max_return, sample_count, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        dist_id, grid_id, json.dumps(sample_list), mean, std,
        positive_ratio, min_val, max_val, new_count, datetime.now().isoformat()
    ))

    # 5. 更新索引表
    confidence = "high" if new_count >= 20 else ("medium" if new_count >= 5 else "low")
    cursor.execute("""
        UPDATE electron_cloud_index
        SET sample_count = ?, confidence_level = ?, distribution_id = ?, last_updated = ?
        WHERE grid_id = ?
    """, (new_count, confidence, dist_id, datetime.now().isoformat(), grid_id))

    conn.commit()
    conn.close()
    print(f"   ✅ 插入: {pattern_id} | {band_position} | return={return_value:.3f} | 总样本={new_count}")


def insert_sample_data():
    """插入10条样本数据"""
    print("=" * 50)
    print("插入10条样本数据到电子云分布表")
    print("=" * 50)

    # 锤子线 (bullish) 在谷底和上升下段的表现
    samples = [
        ("1_bullish_0_hammer", "valley", 0.12),
        ("1_bullish_0_hammer", "valley", 0.08),
        ("1_bullish_0_hammer", "valley", 0.15),
        ("1_bullish_0_hammer", "rise_lower", 0.05),
        ("1_bullish_0_hammer", "rise_lower", 0.03),

        # 射击之星 (bearish) 在峰顶和上升上段的表现
        ("2_bearish_0_shooting_star", "peak", -0.08),
        ("2_bearish_0_shooting_star", "peak", -0.12),
        ("2_bearish_0_shooting_star", "peak", -0.05),
        ("2_bearish_0_shooting_star", "rise_upper", -0.03),
        ("2_bearish_0_shooting_star", "rise_upper", -0.02),
    ]

    for pattern_id, position, ret in samples:
        insert_sample(pattern_id, position, ret)

    print("\n✅ 样本插入完成")


if __name__ == "__main__":
    insert_sample_data()