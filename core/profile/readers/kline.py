# -*- coding: utf-8 -*-
"""
行情档案读取器（2026-08-30 老板：股票=人，数据=档案）
======================================================
读 freestockdb K 线（价量）。只读行情，不算指标（指标归策略/档案组装层）。
"""
from typing import Optional

import pandas as pd

from ..base import BaseProfileReader


class KlineReader(BaseProfileReader):
    """行情档案：code -> {price/open/high/low/volume 日线}"""

    name = "kline"

    def read(self, code: str, date=None, start=None, end=None, **kw) -> dict:
        from core.data_loader import load_data

        code = str(code).zfill(6)
        if date is not None:
            d = pd.Timestamp(date)
            start = start or (d - pd.Timedelta(days=365 * 3)).strftime('%Y-%m-%d')
            end = end or d.strftime('%Y-%m-%d')
        try:
            md = load_data(source='freestockdb', tickers=[code],
                           start=start, end=end, frequency='1d', fq='qfq')
        except Exception:
            return {}
        if code not in md.price.columns:
            return {}
        out = {
            'price': md.price[code].dropna(),
        }
        if md.open_price is not None and code in md.open_price.columns:
            out['open'] = md.open_price[code].dropna()
        if md.high_price is not None and code in md.high_price.columns:
            out['high'] = md.high_price[code].dropna()
        if md.low_price is not None and code in md.low_price.columns:
            out['low'] = md.low_price[code].dropna()
        if md.volume is not None and code in md.volume.columns:
            out['volume'] = md.volume[code].dropna()
        return out

    def latest_close(self, code: str, date) -> Optional[float]:
        """date 当日（或前最近）收盘价；无则 None"""
        k = self.read(code, date=date)
        s = k.get('price')
        if s is None or len(s) == 0:
            return None
        before = s[s.index <= pd.Timestamp(date)]
        if len(before) == 0:
            return None
        return float(before.iloc[-1])
