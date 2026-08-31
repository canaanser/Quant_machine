# -*- coding: utf-8 -*-
"""
元数据档案读取器（2026-08-30 老板：股票=人，数据=档案）
======================================================
读 data/stock_names.json：code -> 股票名称。只读名称，别的不掺和。
"""
import json
import os
from typing import Optional

from config.config import PROJECT_ROOT

from ..base import BaseProfileReader


class MetaReader(BaseProfileReader):
    """元数据档案：code -> {'name': 股票名称}"""

    name = "meta"

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(PROJECT_ROOT, 'data', 'stock_names.json')
        self._names = None

    def _load(self) -> dict:
        if self._names is None:
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    self._names = json.load(f)
            except Exception:
                self._names = {}
        return self._names

    def read(self, code: str, date=None, **kw) -> dict:
        names = self._load()
        code = str(code).zfill(6)
        return {'name': names.get(code)}
