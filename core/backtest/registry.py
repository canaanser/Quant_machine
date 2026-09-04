# -*- coding: utf-8 -*-
"""
注册表工厂（2026-09-02 架构整理 P2：配置驱动装配台）
=====================================================================
from_config 通过字符串 type 实例化策略/闸门——需要注册表把名字映射到类。
参考 core/tags/registry.py 的设计（自动扫描 vs 显式注册——这里先显式，量小）。

用法：
    StrategyRegistry.get("SimpleStrategy")  → SimpleStrategy 类
    GateRegistry.get("WangwenGate")         → WangwenGate 类
新增策略/闸门：register() 一次即可，from_config 不用改。
"""
from typing import Dict, Type

from core.strategy import SimpleStrategy
from core.backtest.gates import WangwenGate


class StrategyRegistry:
    """策略注册表：type 字符串 → 策略类"""
    _registry: Dict[str, Type] = {
        "SimpleStrategy": SimpleStrategy,
    }

    @classmethod
    def register(cls, name: str, strategy_cls: Type) -> None:
        cls._registry[name] = strategy_cls

    @classmethod
    def get(cls, name: str) -> Type:
        if name not in cls._registry:
            raise KeyError(f"未注册的策略类型: {name}（可用: {list(cls._registry)}）")
        return cls._registry[name]

    @classmethod
    def names(cls) -> list:
        return list(cls._registry)


class GateRegistry:
    """闸门注册表：type 字符串 → 闸门类"""
    _registry: Dict[str, Type] = {
        "WangwenGate": WangwenGate,
    }

    @classmethod
    def register(cls, name: str, gate_cls: Type) -> None:
        cls._registry[name] = gate_cls

    @classmethod
    def get(cls, name: str) -> Type:
        if name not in cls._registry:
            raise KeyError(f"未注册的闸门类型: {name}（可用: {list(cls._registry)}）")
        return cls._registry[name]

    @classmethod
    def names(cls) -> list:
        return list(cls._registry)
