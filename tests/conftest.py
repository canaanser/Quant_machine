# -*- coding: utf-8 -*-
"""
pytest 共享夹具（2026-08-26 小二陈）
- 统一把项目根目录加入 sys.path（tests/ 下直接运行或 pytest 从根目录运行均可）
- 提供缓存数据可用性判断（回测类测试依赖本地缓存，无缓存时跳过）
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "stockdb"


def cache_available() -> bool:
    """是否有本地缓存数据（回测回归测试依赖）"""
    return CACHE_DIR.exists() and any(CACHE_DIR.glob("*_1d.csv"))


def pytest_configure(config):
    """注册自定义 marker，避免 PytestUnknownMarkWarning"""
    config.addinivalue_line("markers", "cache: 需要本地 stockdb 缓存数据（无缓存自动跳过）")
