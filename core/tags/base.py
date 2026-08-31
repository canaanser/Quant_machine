# -*- coding: utf-8 -*-
"""
标签生成器基类（2026-08-30 老板：标签归类系统）
=================================================
统一"标签生成器"接口：输入无（读取自有数据源），输出**带有效期**的标签长表。

标签 = 股票 × 时间区间 × 标签值：
  - 标签随时间可变化（valid_from ~ valid_to 区间，同一票可多段不同标签）
  - 规则迭代用 version 区分（同版本幂等，新版本覆盖重算）
  - 可回填：规则改了，重新 generate() 即重算历史

数据契约（generate 返回的 DataFrame 列）：
  code        股票代码（6位，如 '000063'）
  valid_from  标签生效日（含）
  valid_to    标签失效日（含，None=至今仍有效）
  value       标签值（str，如 '震荡票'/'趋势票'）
  version     生成器版本（如 'v1'）

用法：
    class MyTag(BaseTagGenerator):
        name = 'my_tag'
        version = 'v1'
        value_domain = ['A', 'B']
        def generate(self): return DataFrame([...])
"""
from abc import ABC, abstractmethod
from typing import List, Optional

import pandas as pd

#: 标签长表标准列
TAG_COLUMNS = ['code', 'valid_from', 'valid_to', 'value', 'version']


class BaseTagGenerator(ABC):
    """标签生成器基类：generate() 产出带有效期的标签长表"""

    #: 标签名（registry 注册键，子类覆盖）
    name: str = "base"
    #: 方案版本（规则变更 +1，覆盖重算）
    version: str = "v1"
    #: 取值域（合法标签值列表，报告/校验用）
    value_domain: List[str] = []
    #: 附加列（标准 TAG_COLUMNS 之外的扩展列，如 weak/score）
    extra_columns: List[str] = []

    @abstractmethod
    def generate(self, codes: Optional[List[str]] = None,
                 start: Optional[str] = None,
                 end: Optional[str] = None) -> pd.DataFrame:
        """生成标签长表 DataFrame[code, valid_from, valid_to, value, version]

        Args:
            codes: 只生成指定股票（None=全部已加载）
            start/end: 数据范围（生成器可自行决定是否使用）
        """
        raise NotImplementedError

    # ---------- 通用工具 ----------
    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化为标签长表（补全列/类型/排序）"""
        out = df.copy()
        for col in TAG_COLUMNS:
            if col not in out.columns:
                out[col] = None
        cols = list(TAG_COLUMNS)
        for col in self.extra_columns:
            if col in out.columns and col not in cols:
                cols.append(col)
        out = out[cols]
        out['code'] = out['code'].astype(str).str.zfill(6)
        out['valid_from'] = pd.to_datetime(out['valid_from'])
        out['valid_to'] = pd.to_datetime(out['valid_to'])
        out['version'] = out['version'].fillna(self.version)
        return out.sort_values(['code', 'valid_from']).reset_index(drop=True)

    def describe(self) -> str:
        """标签说明（一行）"""
        return f"{self.name}({self.version}): {self.value_domain}"
