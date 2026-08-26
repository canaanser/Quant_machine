# -*- coding: utf-8 -*-
"""
扫描进度/统计查询/位置回填写入
（2026-08-26 小二陈：从 data_writer.py 拆出，接口不变）
"""
from datetime import datetime
from typing import Optional, Dict, Any
from .connection import get_global_connection, _maybe_commit
from .schema import _init_tables

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

    _maybe_commit(conn)

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
    回填单条记录的 band_position，同时设置 band_position_ready：
    位置有效 → ready=1；位置为 unknown（映射失败）→ ready=0（回到 pending）
    修复：此前映射失败把位置改成 unknown 但 ready 未同步，导致 unknown+ready=1 的脏数据
    返回更新的记录数
    """
    _init_tables()

    conn = get_global_connection()
    cursor = conn.cursor()

    ready = 0 if band_position == 'unknown' else 1

    cursor.execute("""
            UPDATE pattern_history
            SET band_position = ?,
                band_progress = ?,
                band_direction = ?,
                band_position_ready = ?,
                band_position_updated_at = ?
            WHERE record_id = ?
    """, (
        band_position,
        band_progress,
        band_direction,
        ready,
        datetime.now().isoformat(),
        record_id
    ))

    _maybe_commit(conn)
    return cursor.rowcount

