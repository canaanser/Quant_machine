# -*- coding: utf-8 -*-
"""
标签池注册表（2026-08-30 老板：标签归类系统）
==============================================
管理所有已注册的标签生成器：
  - register(gen)：注册（name 唯一，重复注册覆盖）
  - unregister(name)：注销
  - list()：列出全部标签（含版本/取值域）
  - get(name)：取生成器实例
  - 自动扫描 generators/ 目录：新加生成器文件即自动注册（即插即用）

数据落盘：
  - labels.json（标签池目录，供前端/App 展示"有哪些标签"）
"""
import importlib
import json
import os
import pkgutil
from typing import Dict, List, Optional

from config import PROJECT_ROOT, TAGS_LABELS_PATH
from .base import BaseTagGenerator

#: 已注册生成器：name -> 实例
_REGISTRY: Dict[str, BaseTagGenerator] = {}


def register(generator: BaseTagGenerator) -> None:
    """注册标签生成器（name 唯一，重复覆盖）"""
    if not isinstance(generator, BaseTagGenerator):
        raise TypeError(f"{generator} 必须是 BaseTagGenerator 实例")
    _REGISTRY[generator.name] = generator
    _save_labels_json()


def unregister(name: str) -> None:
    """注销标签生成器"""
    _REGISTRY.pop(name, None)
    _save_labels_json()


def get(name: str) -> Optional[BaseTagGenerator]:
    """取生成器实例（未注册则尝试扫描目录加载）"""
    if name not in _REGISTRY:
        _scan_generators()
    return _REGISTRY.get(name)


def list_tags() -> List[dict]:
    """列出全部标签：[{name, version, value_domain, desc}]"""
    if not _REGISTRY:
        _scan_generators()
    return [{
        'name': g.name,
        'version': g.version,
        'value_domain': g.value_domain,
        'desc': g.describe(),
    } for g in _REGISTRY.values()]


def _scan_generators() -> None:
    """自动扫描 core/tags/generators/ 下的生成器模块（即插即用）"""
    import core.stocktags.generators as pkg
    for modinfo in pkgutil.iter_modules(pkg.__path__):
        try:
            mod = importlib.import_module(f"{pkg.__name__}.{modinfo.name}")
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if (isinstance(obj, type) and issubclass(obj, BaseTagGenerator)
                        and obj is not BaseTagGenerator and obj.name != 'base'):
                    _REGISTRY[obj.name] = obj()
        except Exception:
            continue


def _save_labels_json() -> None:
    """标签池目录落盘（前端/App 可读）"""
    try:
        os.makedirs(os.path.dirname(TAGS_LABELS_PATH), exist_ok=True)
        with open(TAGS_LABELS_PATH, 'w', encoding='utf-8') as f:
            json.dump({'tags': list_tags(), 'updated': __import__('datetime').datetime.now().isoformat()},
                      f, ensure_ascii=False, indent=2)
    except Exception:
        pass
