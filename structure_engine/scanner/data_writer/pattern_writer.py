# -*- coding: utf-8 -*-
"""
形态历史记录写入（幂等）
（2026-08-26 小二陈：从 data_writer.py 拆出，接口不变）
"""
import uuid
from datetime import datetime
from typing import Optional
from .connection import get_global_connection, _maybe_commit
from .schema import _init_tables

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
    open_price: Optional[float] = None,
    return_1d: float = 0.0, return_2d: float = 0.0,
    return_3d: float = 0.0, return_4d: float = 0.0, return_5d: float = 0.0,
    drawdown_from_peak: Optional[float] = None,
    days_since_peak: Optional[int] = None,
    cooldown_days: Optional[int] = None,
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

    # 幂等写入：同一股票 + 同一形态 + 同一日期只保留一条
    # （消除相邻波段右窗重叠、重复扫描导致的重复记录；match_date 按日期前缀匹配，
    #   兼容 'YYYY-MM-DD' 与 'YYYY-MM-DD HH:MM:SS' 两种格式）
    cursor.execute("""
        SELECT record_id FROM pattern_history
        WHERE symbol = ? AND pattern_id = ? AND substr(match_date, 1, 10) = ?
        LIMIT 1
    """, (symbol, pattern_id, str(match_date)[:10]))
    existing = cursor.fetchone()
    if existing:
        # 幂等命中：补更新 V3 新字段（2026-08-27：重扫时旧记录也要填 open/逐日收益）
        try:
            cursor.execute("""
                UPDATE pattern_history SET
                    open_price = ?,
                    return_1d = ?, return_2d = ?, return_3d = ?, return_4d = ?, return_5d = ?
                WHERE record_id = ?
            """, (open_price, return_1d, return_2d, return_3d, return_4d, return_5d, existing[0]))
            _maybe_commit(conn)
        except Exception:
            pass
        return existing[0]

    cursor.execute("""
        INSERT INTO pattern_history (
            record_id, symbol, pattern_id, pattern_name, category,
            match_date, match_price, open_price,
            peak_date, valley_date,
            band_position, band_progress, band_direction, wave_id,
            band_position_ready, band_position_updated_at,
            return_1d, return_2d, return_3d, return_4d, return_5d,
            drawdown_from_peak, days_since_peak, cooldown_days,
            return_10d, return_20d, composite_return,
            signed_score, base_score, scan_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record_id, symbol, pattern_id, pattern_name, category,
        match_date, match_price, open_price,
        peak_date, valley_date,
        band_position, band_progress, band_direction, wave_id,
        band_position_ready, band_position_updated_at,
        return_1d, return_2d, return_3d, return_4d, return_5d,
        drawdown_from_peak, days_since_peak, cooldown_days,
        return_10d, return_20d, composite_return,
        signed_score, base_score, scan_version, datetime.now().isoformat()
    ))

    _maybe_commit(conn)
    return record_id
