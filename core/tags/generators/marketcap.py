# -*- coding: utf-8 -*-
"""
市值标签生成器（2026-08-30 标签系统演示：第二块标签）
======================================================
按最新总市值分档（从本地每日估值 data/info/fundamentals/daily/ 读取）：
  大盘: total_mv >= 1000亿
  中盘: 100亿 <= total_mv < 1000亿
  小盘: total_mv < 100亿
标签 = 时间区间（用估值数据的时间范围，市值会变→多段区间）
"""
from typing import List, Optional

import pandas as pd

from ...data_loader import load_data
from ..base import BaseTagGenerator
from config import PROJECT_ROOT, FUNDAMENTALS_DAILY_DIR
import os


class MarketCapGenerator(BaseTagGenerator):
    """市值标签：大盘/中盘/小盘"""

    name = "marketcap"
    version = "v1"
    value_domain = ['大盘', '中盘', '小盘']

    LARGE = 1000e8    # 大盘 >= 1000亿
    MID = 100e8       # 中盘 >= 100亿

    def generate(self, codes: Optional[List[str]] = None,
                 start: Optional[str] = None,
                 end: Optional[str] = None) -> pd.DataFrame:
        rows = []
        d = os.path.join(PROJECT_ROOT, FUNDAMENTALS_DAILY_DIR)
        for f in os.listdir(d):
            if not f.endswith('.csv'):
                continue
            code = f[:6]
            if codes is not None and code not in set(codes):
                continue
            try:
                df = pd.read_csv(os.path.join(d, f))
                if 'total_mv' not in df.columns or len(df) == 0:
                    continue
                mv = df['total_mv'].dropna()
                if len(mv) == 0:
                    continue
                # 简单版：按最新市值打一个全程标签（演示用；真实可按时段切）
                latest_mv = float(mv.iloc[-1])
                if latest_mv >= self.LARGE:
                    value = '大盘'
                elif latest_mv >= self.MID:
                    value = '中盘'
                else:
                    value = '小盘'
                rows.append({
                    'code': code,
                    'valid_from': pd.Timestamp('2017-01-01'),
                    'valid_to': pd.Timestamp('2026-08-28'),
                    'value': value,
                    'version': self.version,
                })
            except Exception:
                continue
        return self.normalize(pd.DataFrame(rows))
