"""
电子云模型构建器（electron_cloud_builder.py）
============================================
线A：从 pattern_history 聚合历史样本，回填电子云三层表。

职责：
  1. 遍历 pattern_history 中所有 (pattern_id × band_position) 格子（ready=1）
  2. 每个格子计算：样本量 / 均值 / 标准差 / 胜率 / 极值 / 分位数(p25/p50/p75)
  3. 写入 electron_cloud_index（格子索引）+ electron_cloud_distribution（分布）
  4. 幂等：同格子重新构建时更新（upsert）

设计要点：
  - 只统计 band_position_ready=1 的记录（位置已确认）
  - 分位数存入 distribution.sample_list（JSON），不改表结构
  - 置信度：≥20 high / ≥5 medium / <5 low

用法：
  python -m structure_engine.cloud.electron_cloud_builder   # 全量回填
  from structure_engine.cloud.electron_cloud_builder import rebuild_all
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

# ===== 统一数据库路径（与 data_writer.py 一致：真实库） =====
PROJECT_ROOT = Path(__file__).parent.parent.parent
from config.config import PATTERN_DB_PATH as DB_PATH  # 统一路径（2026-08-26）

MIN_SAMPLES_HIGH = 20      # 置信度 high 阈值
MIN_SAMPLES_MEDIUM = 5     # 置信度 medium 阈值


def get_connection():
    """获取数据库连接"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(DB_PATH))


def _confidence(sample_count: int) -> str:
    if sample_count >= MIN_SAMPLES_HIGH:
        return "high"
    if sample_count >= MIN_SAMPLES_MEDIUM:
        return "medium"
    return "low"


def build_cell(cursor, pattern_id: str, band_position: str) -> Optional[Dict]:
    """
    构建单个格子（形态×位置）的分布统计。
    返回统计 dict（写入 distribution 表），格子无样本返回 None。
    """
    cursor.execute("""
        SELECT composite_return FROM pattern_history
        WHERE pattern_id = ? AND band_position = ?
          AND band_position_ready = 1 AND composite_return IS NOT NULL
    """, (pattern_id, band_position))
    rows = cursor.fetchall()

    if not rows:
        return None

    values = np.array([r[0] for r in rows], dtype=float)
    n = len(values)
    mean = float(values.mean())
    std = float(values.std(ddof=0))
    positive_ratio = float((values > 0).mean())
    p25, p50, p75 = [float(v) for v in np.percentile(values, [25, 50, 75])]

    stat = {
        "sample_count": n,
        "mean_return": round(mean, 6),
        "std_return": round(std, 6),
        "positive_ratio": round(positive_ratio, 4),
        "min_return": round(float(values.min()), 6),
        "max_return": round(float(values.max()), 6),
        "percentiles": {"p25": round(p25, 6), "p50": round(p50, 6), "p75": round(p75, 6)},
        "confidence_level": _confidence(n),
    }
    return stat


def upsert_cell(cursor, pattern_id: str, band_position: str, stat: Dict) -> None:
    """
    写入/更新格子（幂等 upsert）：
      electron_cloud_index 按 (pattern_id, band_position) 唯一；
      electron_cloud_distribution 每次构建追加新版本（保留历史）。
    """
    grid_id = f"{pattern_id}_{band_position}"
    now = datetime.now().isoformat()
    dist_id = f"DIST-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    # 索引表 upsert
    cursor.execute("""
        INSERT INTO electron_cloud_index (grid_id, pattern_id, band_position,
                                          sample_count, confidence_level, distribution_id, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(grid_id) DO UPDATE SET
            sample_count = excluded.sample_count,
            confidence_level = excluded.confidence_level,
            distribution_id = excluded.distribution_id,
            last_updated = excluded.last_updated
    """, (grid_id, pattern_id, band_position, stat["sample_count"],
          stat["confidence_level"], dist_id, now))

    # 分布表追加新版本（保留历史，查询取最新）
    sample_list_json = json.dumps({
        "percentiles": stat["percentiles"],
        "generated_at": now,
    }, ensure_ascii=False)
    cursor.execute("""
        INSERT INTO electron_cloud_distribution (
            distribution_id, grid_id, sample_list, mean_return, std_return,
            positive_ratio, min_return, max_return, sample_count, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (dist_id, grid_id, sample_list_json, stat["mean_return"], stat["std_return"],
          stat["positive_ratio"], stat["min_return"], stat["max_return"],
          stat["sample_count"], now))


def rebuild_all() -> Dict:
    """
    全量回填：遍历 pattern_history 所有 (pattern_id, band_position) 格子并构建。
    返回统计摘要。
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 所有格子组合（ready=1 且有样本）
    cursor.execute("""
        SELECT pattern_id, band_position, COUNT(*) as cnt
        FROM pattern_history
        WHERE band_position_ready = 1 AND composite_return IS NOT NULL
          AND band_position IS NOT NULL AND band_position != ''
        GROUP BY pattern_id, band_position
        ORDER BY pattern_id, band_position
    """)
    cells = cursor.fetchall()

    built, skipped = 0, 0
    summary = {"cells": [], "total_samples": 0}

    for pattern_id, band_position, _cnt in cells:
        stat = build_cell(cursor, pattern_id, band_position)
        if stat is None:
            skipped += 1
            continue
        upsert_cell(cursor, pattern_id, band_position, stat)
        summary["cells"].append({
            "pattern_id": pattern_id,
            "band_position": band_position,
            "sample_count": stat["sample_count"],
            "confidence": stat["confidence_level"],
            "mean_return": stat["mean_return"],
            "positive_ratio": stat["positive_ratio"],
        })
        summary["total_samples"] += stat["sample_count"]
        built += 1

    conn.commit()
    conn.close()
    summary["built"] = built
    summary["skipped"] = skipped
    return summary


# ============================================================
# progress 分桶统计（动态位置编码的早期数据积累）
# 老板预留的 band_progress 字段在此发挥作用：
#   短波段分不出 8 格离散位置，但 progress（0~1 连续进度）始终存在。
#   按 形态 × 波段方向 × progress 桶(0.1) 统计收益分布，
#   与 8 格位置权重并存，互为补充。
# ============================================================

PROGRESS_BUCKETS = 10  # progress 0~1 分 10 桶（每桶 0.1）


def _init_progress_table(cursor):
    """建 progress 分桶表（若不存在）"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS progress_return_map (
            map_id TEXT PRIMARY KEY,
            pattern_id TEXT NOT NULL,
            band_direction TEXT NOT NULL,        -- rise / fall（progress 语义随方向不同）
            progress_bucket INTEGER NOT NULL,    -- 0~9（0.0-0.1 为 0，... 0.9-1.0 为 9）
            sample_count INTEGER DEFAULT 0,
            mean_return REAL,
            std_return REAL,
            positive_ratio REAL,
            percentiles_json TEXT,               -- {"p25":..,"p50":..,"p75":..}
            confidence_level TEXT,
            created_at TEXT,
            UNIQUE(pattern_id, band_direction, progress_bucket)
        )
    """)


def build_progress_map(conn=None) -> Dict:
    """
    按 形态 × 方向 × progress桶 统计收益分布。
    短波段（<10天）的形态位置无法细分 8 格，但 progress 始终有效——
    本表让这些样本以连续位置方式参与统计。
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cursor = conn.cursor()

    _init_progress_table(cursor)

    # 读取所有带有效 progress 的记录（含短波段）
    # 注意：pattern_history.band_direction 存的是 'up'/'down'（wave_detector 的 direction）
    cursor.execute("""
        SELECT pattern_id, band_direction, band_progress, composite_return
        FROM pattern_history
        WHERE band_progress IS NOT NULL AND band_progress >= 0
          AND band_direction IN ('up', 'down')
          AND composite_return IS NOT NULL
    """)
    rows = cursor.fetchall()

    from collections import defaultdict
    buckets = defaultdict(list)  # (pattern_id, direction, bucket) -> [returns]

    for pattern_id, direction, progress, ret in rows:
        bucket = min(int(progress * PROGRESS_BUCKETS), PROGRESS_BUCKETS - 1)
        buckets[(pattern_id, direction, bucket)].append(ret)

    now = datetime.now().isoformat()
    built = 0
    for (pattern_id, direction, bucket), rets in buckets.items():
        arr = np.array(rets, dtype=float)
        n = len(arr)
        mean = float(arr.mean())
        std = float(arr.std(ddof=0))
        pr = float((arr > 0).mean())
        p25, p50, p75 = [float(v) for v in np.percentile(arr, [25, 50, 75])]
        conf = _confidence(n)
        map_id = f"PRG-{pattern_id}-{direction}-{bucket}"

        cursor.execute("""
            INSERT INTO progress_return_map (
                map_id, pattern_id, band_direction, progress_bucket,
                sample_count, mean_return, std_return, positive_ratio,
                percentiles_json, confidence_level, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pattern_id, band_direction, progress_bucket) DO UPDATE SET
                sample_count = excluded.sample_count,
                mean_return = excluded.mean_return,
                std_return = excluded.std_return,
                positive_ratio = excluded.positive_ratio,
                percentiles_json = excluded.percentiles_json,
                confidence_level = excluded.confidence_level,
                created_at = excluded.created_at
        """, (
            map_id, pattern_id, direction, bucket, n,
            round(mean, 6), round(std, 6), round(pr, 4),
            json.dumps({"p25": round(p25, 6), "p50": round(p50, 6), "p75": round(p75, 6)}, ensure_ascii=False),
            conf, now
        ))
        built += 1

    conn.commit()
    if own_conn:
        conn.close()
    return {"built": built, "total_samples": sum(len(v) for v in buckets.values())}


def main():
    print("🚀 电子云数据回填启动...")
    print(f"📂 数据库: {DB_PATH}")
    result = rebuild_all()
    print(f"\n✅ 构建完成: {result['built']} 个格子（跳过 {result['skipped']}），样本合计 {result['total_samples']}")
    print("\n=== 格子分布（按置信度）===")
    from collections import Counter
    conf = Counter(c["confidence"] for c in result["cells"])
    for k in ["high", "medium", "low"]:
        print(f"  {k}: {conf.get(k, 0)} 个格子")
    print("\n=== 样本量 Top10 格子 ===")
    for c in sorted(result["cells"], key=lambda x: -x["sample_count"])[:10]:
        print(f"  {c['pattern_id']:<40} {c['band_position']:<12} n={c['sample_count']:<5} 均值={c['mean_return']:+.4f} 胜率={c['positive_ratio']:.0%} {c['confidence']}")

    print("\n🚀 progress 分桶统计启动（动态位置编码早期积累）...")
    pr = build_progress_map()
    print(f"✅ progress 分桶完成: {pr['built']} 个桶，样本合计 {pr['total_samples']}")


if __name__ == "__main__":
    main()
