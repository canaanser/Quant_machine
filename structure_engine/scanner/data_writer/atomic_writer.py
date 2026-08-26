# -*- coding: utf-8 -*-
"""
原子特征记录写入（幂等）
（2026-08-26 小二陈：从 data_writer.py 拆出，接口不变）
"""
import uuid
from datetime import datetime
from typing import Dict
from .connection import get_global_connection, _maybe_commit
from .schema import _init_tables

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

    # 幂等写入：同一股票同一日期同一形态只保留一条原子特征
    cursor.execute("""
        SELECT record_id FROM atomic_features
        WHERE symbol = ? AND date = ? AND pattern_id = ?
        LIMIT 1
    """, (symbol, date, pattern_id))
    existing = cursor.fetchone()
    if existing:
        return existing[0]

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

    _maybe_commit(conn)
    return record_id
