# -*- coding: utf-8 -*-
"""
数据写入层（2026-08-26 小二陈：从 data_writer.py 拆分为包，接口不变）
  connection.py  连接管理（全局连接/批量模式/版本）
  schema.py      表结构定义与初始化
  pattern_writer / atomic_writer / wave_writer / scan_writer  各写入
"""

from .connection import (
    DB_PATH, SCHEMA_VERSION,
    set_batch_mode, _maybe_commit, get_global_connection, close_global_connection,
)
from .schema import _init_tables
from .pattern_writer import write_pattern_history
from .atomic_writer import write_atomic_features
from .wave_writer import write_wave_history
from .scan_writer import (
    update_scan_progress, get_last_scan_progress, get_pattern_history_count,
    get_pending_records_in_range, update_band_position,
)

__all__ = [
    'DB_PATH', 'SCHEMA_VERSION',
    'set_batch_mode', '_maybe_commit', 'get_global_connection', 'close_global_connection',
    '_init_tables',
    'write_pattern_history', 'write_atomic_features', 'write_wave_history',
    'update_scan_progress', 'get_last_scan_progress', 'get_pattern_history_count',
    'get_pending_records_in_range', 'update_band_position',
]
