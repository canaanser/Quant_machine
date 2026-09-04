# -*- coding: utf-8 -*-
"""
Pipeline 配置（2026-09-02 架构整理 P2：配置驱动装配台）
=====================================================================
配置是纯数据（dict/YAML），不是代码——换实验 = 换配置，不改脚本/核心。

P2-1 支持范围（只含已存在的模块，超前的不接）：
  - 策略：SimpleStrategy（注册表可扩）
  - 闸门：WangwenGate（ww_min 进场 / ww_exit 退出）
  - risk：top_n / stop_loss / take_profit / 单票/总仓上限
趋势门/大盘门等类切出来后再进 config（P2-4）。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .registry import StrategyRegistry, GateRegistry


@dataclass
class PipelineConfig:
    """Pipeline 配置清单（纯数据）"""

    name: str = "unnamed"
    description: str = ""
    strategy: Dict[str, Any] = field(default_factory=dict)
    gates: List[Dict[str, Any]] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    risk: Dict[str, Any] = field(default_factory=dict)   # 只写想覆盖的键，其余用默认
    output: Dict[str, Any] = field(default_factory=dict)

    def merged_risk(self) -> dict:
        """默认风控 + 配置覆盖（2026-09-02 修复：不能传残 dict 覆盖默认）"""
        import copy
        from config.risk_config import DEFAULT_RISK_CONFIG
        rc = copy.deepcopy(DEFAULT_RISK_CONFIG)
        rc.update(self.risk or {})
        return rc

    # ---------- 加载 ----------
    @classmethod
    def from_dict(cls, data: dict) -> "PipelineConfig":
        return cls(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            strategy=data.get("strategy", {}),
            gates=data.get("gates", []),
            data=data.get("data", {}),
            risk=data.get("risk", {}),
            output=data.get("output", {}),
        )

    @classmethod
    def from_yaml(cls, path: str) -> "PipelineConfig":
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    # ---------- 校验 ----------
    def validate(self) -> List[str]:
        """配置合法性检查，返回错误列表（空=通过）"""
        errs = []
        if not self.strategy.get("type"):
            errs.append("strategy.type 缺失")
        else:
            try:
                StrategyRegistry.get(self.strategy["type"])
            except KeyError as e:
                errs.append(str(e))
        for g in self.gates:
            t = g.get("type")
            if not t:
                errs.append("gates[].type 缺失")
                continue
            try:
                GateRegistry.get(t)
            except KeyError as e:
                errs.append(str(e))
        return errs


def build_strategy(cfg: Dict[str, Any]):
    """按 config.strategy 实例化策略"""
    cls = StrategyRegistry.get(cfg["type"])
    return cls(**cfg.get("params", {}))


def build_gates(cfg_list: List[Dict[str, Any]]) -> List:
    """按 config.gates 实例化闸门列表"""
    gates = []
    for g in cfg_list:
        cls = GateRegistry.get(g["type"])
        gates.append(cls(**g.get("params", {})))
    return gates
