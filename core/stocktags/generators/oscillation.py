# -*- coding: utf-8 -*-
"""
震荡度标签生成器（2026-08-30 老板：标签归类系统第一块基石）
============================================================
特征（老板"万年绕着一个价震荡"的量化）：
  ① 中枢漂移度 center_stab = ma250.std()/ma250.mean()   —— 价格绕固定中枢 vs 大幅漂移
  ② 均值回归相关 reg_corr = corr(dev, fwd20)            —— <0 偏离后回归（震荡）/ >0 动量延续（趋势）
  ③ 十年价格区间比 range_ratio = max/min                —— 窄幅 vs 大趋势

标签规则（基于中兴/中钨/新易盛对照校准）：
  震荡票: center_stab < 0.25 且 reg_corr < 0 且 range_ratio < 10  → 适合价格带/回归策略
  趋势票: 不满足震荡条件                                          → 适合趋势策略

数据源：freestockdb 日K（本地 HTTP，不烧在线限额）
"""
from typing import List, Optional

import numpy as np
import pandas as pd

from ...data_loader import load_data
from ..base import BaseTagGenerator


class OscillationGenerator(BaseTagGenerator):
    """震荡度标签：震荡票（价格带策略）/ 趋势票（趋势策略）"""

    name = "oscillation"
    version = "v1"
    value_domain = ['震荡票', '趋势票']

    #: 震荡票判定阈值
    CENTER_STAB_MAX = 0.25   # 中枢漂移度上限（<0.25 稳定中枢）
    REG_CORR_MAX = 0.0       # 均值回归相关（<0 偏离后回归）
    RANGE_MAX = 10.0         # 十年价格区间比（<10x 窄幅）

    def generate(self, codes: Optional[List[str]] = None,
                 start: Optional[str] = '2017-01-01',
                 end: Optional[str] = '2026-08-28') -> pd.DataFrame:
        from config.config import SCAN_TICKERS, SCAN_TICKERS_CURATED
        start = start or '2017-01-01'   # None 时用默认（produce 可能传 None）
        end = end or '2026-08-28'
        all_codes = list(SCAN_TICKERS)
        if codes is not None:
            all_codes = [c for c in all_codes if c in set(codes)]
        rows = []
        for code in all_codes:
            try:
                md = load_data(source='freestockdb', tickers=[code], start=start, end=end,
                               frequency='1d', fq='qfq')
                px = md.price[code].dropna()
                if len(px) < 250:
                    continue
                ma250 = px.rolling(250, min_periods=100).mean()
                if ma250.mean() <= 0:
                    continue
                center_stab = ma250.std() / ma250.mean()
                dev = (px / ma250 - 1).dropna()
                reg = []
                for i in range(0, len(px) - 20, 5):
                    if pd.isna(ma250.iloc[i]):
                        continue
                    reg.append((px.iloc[i] / ma250.iloc[i] - 1, px.iloc[i + 20] / px.iloc[i] - 1))
                reg_corr = 0.0
                if len(reg) > 10:
                    reg_corr = pd.DataFrame(reg, columns=['d', 'f']).corr().iloc[0, 1]
                    if pd.isna(reg_corr):
                        reg_corr = 0.0
                range_ratio = px.max() / px.min() if px.min() > 0 else 99
                is_osc = (center_stab < self.CENTER_STAB_MAX
                          and reg_corr < self.REG_CORR_MAX
                          and range_ratio < self.RANGE_MAX)
                rows.append({
                    'code': code,
                    'valid_from': pd.Timestamp(px.index[0]),
                    'valid_to': pd.Timestamp(px.index[-1]),
                    'value': '震荡票' if is_osc else '趋势票',
                    'version': self.version,
                })
            except Exception:
                continue
        return self.normalize(pd.DataFrame(rows))
