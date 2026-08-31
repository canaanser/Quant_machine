# -*- coding: utf-8 -*-
"""
基本面档案读取器（2026-08-30 老板：股票=人，数据=档案）
========================================================
两类数据，各读各的（干湿分离）：
  - daily/  ：每日估值（pe_ttm/pb/总市值/是否ST）→ 按 date 取 T 日实时值
  - reports/：财报 indicator 期表（pubDate/statDate）→ 按 pubDate ≤ T 取最新一期（无前视）
与 selection/wangwen.py 读取口径一致（同一份文件、同一规则）。
"""
import glob
import json
import os
from bisect import bisect_right
from typing import Dict, List, Optional, Tuple

import pandas as pd

from config.config import PROJECT_ROOT, FUNDAMENTALS_DAILY_DIR, FUNDAMENTALS_REPORTS_DIR

from ..base import BaseProfileReader


class FundamentalsReader(BaseProfileReader):
    """基本面档案：code -> {'realtime': {...}, 'latest_indicator': {...}}"""

    name = "fundamentals"

    def __init__(self, fund_dir: Optional[str] = None, online_dir: Optional[str] = None):
        self.fund_dir = fund_dir or os.path.join(PROJECT_ROOT, FUNDAMENTALS_DAILY_DIR)
        self.online_dir = online_dir or os.path.join(PROJECT_ROOT, FUNDAMENTALS_REPORTS_DIR)
        # 惰性加载缓存（首次 read 时构建）
        self._pe_pb: Dict[str, pd.DataFrame] = {}
        self._ind_series: Dict[str, List[Tuple[pd.Timestamp, dict]]] = {}
        self._loaded = False

    # ---------- 数据加载 ----------
    def _load(self) -> None:
        if self._loaded:
            return
        for f in glob.glob(os.path.join(self.fund_dir, '*.csv')):
            code = os.path.basename(f)[:6]
            try:
                df = pd.read_csv(f, encoding='utf-8')
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date')
                if len(df):
                    self._pe_pb[code] = df
            except Exception:
                continue
        for f in glob.glob(os.path.join(self.online_dir, '*.csv')):
            try:
                df = pd.read_csv(f, encoding='utf-8')
                code = str(df['code'].iloc[0]).zfill(6)
                ind = json.loads(df['indicator'].iloc[0]) if 'indicator' in df.columns and pd.notna(df['indicator'].iloc[0]) else []
                rows = []
                for r in ind:
                    pub = r.get('pubDate') or r.get('statDate')
                    if not pub:
                        continue
                    rows.append((pd.Timestamp(pub), r))
                rows.sort(key=lambda x: x[0])
                if rows:
                    self._ind_series[code] = rows
            except Exception:
                continue
        self._loaded = True

    # ---------- 查询 ----------
    def latest_indicator(self, code: str, date) -> Optional[dict]:
        """pubDate ≤ date 的最新一期 indicator dict（无则 None）"""
        self._load()
        series = self._ind_series.get(str(code).zfill(6))
        if not series:
            return None
        pubs = [p for p, _ in series]
        i = bisect_right(pubs, pd.Timestamp(date)) - 1
        if i < 0:
            return None
        return series[i][1]

    def realtime(self, code: str, date) -> dict:
        """T 日（或 T 前最近）实时 pe_ttm/pb/total_mv/is_st"""
        self._load()
        df = self._pe_pb.get(str(code).zfill(6))
        if df is None or len(df) == 0:
            return {}
        d = pd.Timestamp(date)
        before = df[df['date'] <= d]
        if len(before) == 0:
            return {}
        row = before.iloc[-1]
        out = {}
        for col in ('pe_ttm', 'pb', 'total_mv', 'float_mv', 'close', 'is_st'):
            if col in df.columns:
                v = row[col]
                if pd.notna(v):
                    out[col] = bool(v) if col == 'is_st' else float(v)
        return out

    def read(self, code: str, date=None, **kw) -> dict:
        code = str(code).zfill(6)
        out = {}
        if date is not None:
            out['realtime'] = self.realtime(code, date)
            out['latest_indicator'] = self.latest_indicator(code, date)
        return out
