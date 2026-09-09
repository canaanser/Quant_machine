# -*- coding: utf-8 -*-
"""
标签档案读取器（2026-08-30 老板：标签归类系统）
================================================
读取某票的标签档案（震荡/市值/王文五……），来源 core/tags（虚拟，不落盘）。
"""
from typing import Dict, List, Optional

from ..base import BaseProfileReader


class TagsReader(BaseProfileReader):
    """标签档案：code -> {tag_name: value}（某日）"""

    name = "tags"

    def __init__(self, tag_names: Optional[List[str]] = None):
        #: None = 全部已注册标签；否则只读指定标签
        self.tag_names = tag_names

    def read(self, code: str, date=None, **kw) -> dict:
        from core.stocktags import list_tags, tag_at
        names = self.tag_names or [t['name'] for t in list_tags()]
        out = {}
        for t in names:
            v = tag_at(code, date, t) if date is not None else None
            if v is not None:
                out[t] = v
        return out
