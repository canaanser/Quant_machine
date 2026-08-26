# -*- coding: utf-8 -*-
"""
统一日志模块（2026-08-26 小二陈）
=================================
将散落的 print 调试输出收敛为 logging 分级日志：
- DEBUG：verbose 调试细节（形态融合过程、扫描跳过原因等）
- INFO ：过程信息（数据加载、扫描进度、成交记录）
- WARNING：可恢复的异常（数据缺失、回退路径、跳过项）
- ERROR：不可恢复的错误

用法：
    from core.logger import get_logger
    logger = get_logger(__name__)
    logger.debug("...")
    logger.info("...")

级别控制：
- 控制台 handler 固定 INFO 级（DEBUG 信息默认不刷屏；需要时在调用处
  临时设 logger.setLevel(logging.DEBUG)）
- 模块内通过 logging.getLogger(name).setLevel 可独立调级别
"""
import logging
import sys

_configured = False


def get_logger(name: str = None) -> logging.Logger:
    """获取统一配置的 logger（首次调用时初始化全局配置）"""
    global _configured
    if not _configured:
        _configure_root()
        _configured = True
    return logging.getLogger(name or __name__)


def _configure_root() -> None:
    """配置根 logger：控制台 handler + 可选文件 handler"""
    # 避免重复配置（多模块导入时）
    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(logging.INFO)  # 默认 INFO：debug 不显示

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG)  # handler 不挡 debug，由 logger 级别控制
    console.setFormatter(fmt)
    root.addHandler(console)
