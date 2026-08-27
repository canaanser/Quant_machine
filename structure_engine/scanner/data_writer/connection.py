# -*- coding: utf-8 -*-
"""
数据库连接管理（全局连接/批量模式/表结构版本）
（2026-08-26 小二陈：从 data_writer.py 拆出，接口不变）
"""
import sqlite3
from pathlib import Path
from config.config import PATTERN_DB_PATH as DB_PATH

# ===== 数据库路径 =====
PROJECT_ROOT = Path(__file__).parent.parent.parent
from config.config import PATTERN_DB_PATH as DB_PATH  # 统一路径（2026-08-26）

# ===== 全局数据库连接（复用，避免锁冲突） =====
_global_conn = None

# ===== 批量写入模式（性能优化，2026-08-26 小二陈） =====
# 扫描器在 scan_symbol 开始时开启批量模式，写库攒批后统一 commit：
#   1. 消除每记录一次 fsync 的 IO 瓶颈（之前 3 万+ 条 × 逐条 commit）
#   2. 批量模式外（低频/独立操作）保持逐条 commit，不影响其他调用方
_batch_mode = False

# ===== 表结构版本号 =====
# 修改任何建表/加字段逻辑时 +1，使 _init_tables 缓存失效并重新初始化
SCHEMA_VERSION = 2
_initialized_version = None


def set_batch_mode(enabled: bool):
    """开启/关闭批量写入模式。批量模式下 commit 由调用方统一控制。"""
    global _batch_mode
    _batch_mode = bool(enabled)


def _maybe_commit(conn):
    """批量模式下不自动 commit（攒批），非批量模式保持逐条 commit"""
    if not _batch_mode:
        conn.commit()


def _get_connection():
    """获取数据库连接，确保目录存在"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    # 性能优化（2026-08-27 小二陈）：WAL + 降低同步频率 + 大页缓存 + 忙等待
    # 解决"库越大写入越慢"：commit 从全量刷盘变为追加日志，fsync 次数大减
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")
        conn.execute("PRAGMA busy_timeout=30000")
    except Exception:
        pass
    return conn


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


