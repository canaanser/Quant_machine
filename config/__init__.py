"""
配置包（2026-08-26 小二陈：合并，消除双份冲突）
单一事实源为 config/config.py——所有配置参数/函数经此处转发。
之前 config/__init__.py 自带一份同名参数（COMMISSION=0.001 等），
与 config.py（COMMISSION=0.00012 万一点二）冲突，已统一为 config.py 的值。
"""

from .risk_config import DEFAULT_RISK_CONFIG
from .config import *  # noqa: F401,F403 —— 全部配置从 config.py 转发（__all__ 控制）
