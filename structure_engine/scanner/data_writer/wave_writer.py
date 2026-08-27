# -*- coding: utf-8 -*-
"""
波段记录写入（幂等）
（2026-08-26 小二陈：从 data_writer.py 拆出，接口不变）
"""
import hashlib
from datetime import datetime
from .connection import get_global_connection, _maybe_commit
from .schema import _init_tables

def _make_wave_id(symbol: str, wave: dict) -> str:
    """确定性 wave_id：同一股票同一波段（方向+峰谷日期）永远生成同一 id。
    修复（2026-08-27）：原 uuid4 随机 4 hex 只有 16bit 空间，记录一多必碰撞，
    UNIQUE 约束把整条波段记录丢弃。改为 sha1 前 12 hex（48bit），碰撞概率≈0，
    且重扫同波段幂等命中。"""
    key = f"{symbol}|{wave.get('direction')}|{wave.get('peak_date')}|{wave.get('valley_date')}"
    return "WAVE-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

def write_wave_history(symbol: str, wave: dict, scan_version: int = 1) -> str:
    """写入波段记录表"""
    _init_tables()

    wave_id = _make_wave_id(symbol, wave)

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

    # 幂等写入：同一股票同一波段（类型 + 起止日期）只保留一条
    cursor.execute("""
        SELECT wave_id FROM wave_history
        WHERE symbol = ? AND wave_type = ? AND start_date = ? AND end_date = ?
        LIMIT 1
    """, (symbol, wave_type, start_date, end_date))
    existing = cursor.fetchone()
    if existing:
        return existing[0]

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

    _maybe_commit(conn)
    return wave_id
