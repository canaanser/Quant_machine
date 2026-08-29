# -*- coding: utf-8 -*-
"""
王文五标准滚动选池筛选器（2026-08-30 老板核心目的：替代窥探式静态精选池）
===========================================================================
标准（日斗投资董事长王文）：
  ① 低估值：pe < 30 且 pb < 5 且 pe > 0（用 T 日实时估值）
  ② 高现金流：经营现金流/营业利润 ocf_to_operating_profit > 0.5（用最新披露财报）
  ③ 高分红：接口未找到，暂缺（待 akshare / 正式版接口）
  ④ 业务可持续：毛利率 > 20% 且 净利率 > 0（用最新披露财报）
  ⑤ 有梦想（成长）：营收同比 > 0 且 净利同比 > 0（用最新披露财报）

滚动（walk-forward）机制——无未来函数：
  - 每日 T：估值①用 T 日实时 pe_ttm/pb（本地每日估值快照，每日可得）
  - ②④⑤用 indicator 表中 pubDate ≤ T 的最新一期财报指标（披露日之后才可用）
  - 全符合 → 当日入池。回测里 buy_list 只从当日池内选。

数据（Information 层，路径由 config 统一管理）：
  - 每日估值快照：data/info/fundamentals/daily/{code}.csv（84 只，2020-01-02 ~ 2026-08-28）
  - 定期财报期表：data/info/fundamentals/reports/{code}.csv（indicator 表，每期含 pubDate/statDate）
"""
import glob
import json
import os
from bisect import bisect_right
from typing import Dict, List, Optional, Tuple

import pandas as pd

from config import PROJECT_ROOT, FUNDAMENTALS_DAILY_DIR, FUNDAMENTALS_REPORTS_DIR
from .base import BaseSelector

# ================= 王文五绝对阈值（与 scripts/wangwen_five.py 一致） =================
TH_PE_MAX = 30.0     # ① pe < 30
TH_PB_MAX = 5.0      # ① pb < 5
TH_OCF = 0.5         # ② 经营现金流/营业利润 > 0.5
TH_GROSS = 20.0      # ④ 毛利率 > 20%
TH_NET = 0.0         # ④ 净利率 > 0
TH_REV_YOY = 0.0     # ⑤ 营收同比 > 0
TH_NP_YOY = 0.0      # ⑤ 净利同比 > 0


class WangwenSelector(BaseSelector):
    """王文五标准滚动选池：每日 T 返回符合标准的票集合（无未来函数）"""

    name = "wangwen"

    def __init__(self, fund_dir: Optional[str] = None,
                 online_dir: Optional[str] = None):
        self.fund_dir = fund_dir or os.path.join(PROJECT_ROOT, FUNDAMENTALS_DAILY_DIR)
        self.online_dir = online_dir or os.path.join(PROJECT_ROOT, FUNDAMENTALS_REPORTS_DIR)
        self._pe_pb: Dict[str, pd.DataFrame] = {}       # code -> DataFrame(date, pe_ttm, pb) 已排序
        self._ind_series: Dict[str, List[Tuple[pd.Timestamp, dict]]] = {}  # code -> [(pubDate, 指标dict)]
        self._load()

    # ---------- 数据加载 ----------
    def _load(self) -> None:
        """加载本地每日估值 + 在线财报 indicator 期表（启动一次，查询 O(log n)）"""
        # 本地每日估值
        for f in glob.glob(os.path.join(self.fund_dir, '*.csv')):
            code = os.path.basename(f)[:6]
            try:
                df = pd.read_csv(f, encoding='utf-8')
                df['date'] = pd.to_datetime(df['date'])
                df = df[['date', 'pe_ttm', 'pb']].dropna(subset=['pe_ttm', 'pb']).sort_values('date')
                if len(df):
                    self._pe_pb[code] = df
            except Exception:
                continue
        # 在线财报 indicator 期表
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

    # ---------- 查询 ----------
    def latest_indicator(self, code: str, date):
        """pubDate ≤ date 的最新一期 indicator dict（无则 None）"""
        series = self._ind_series.get(code)
        if not series:
            return None
        pubs = [p for p, _ in series]
        i = bisect_right(pubs, pd.Timestamp(date)) - 1
        if i < 0:
            return None
        return series[i][1]

    def realtime_pe_pb(self, code: str, date) -> Tuple[Optional[float], Optional[float]]:
        """T 日（或 T 前最近）实时 pe_ttm/pb；无数据返回 (None, None)"""
        df = self._pe_pb.get(code)
        if df is None or len(df) == 0:
            return None, None
        d = pd.Timestamp(date)
        idx = df.index[df['date'] <= d]
        if len(idx) == 0:
            return None, None
        row = df.loc[idx[-1]]
        return float(row['pe_ttm']), float(row['pb'])

    # ---------- 标准判定 ----------
    def is_eligible(self, code: str, date) -> bool:
        """单票在 date 日是否符合王文五绝对阈值（①估值用实时，②④⑤用最新披露财报）"""
        # ① 低估值（实时）
        pe, pb = self.realtime_pe_pb(code, date)
        if pe is None or pb is None:
            return False
        if not (0 < pe < TH_PE_MAX and pb < TH_PB_MAX):
            return False
        # ②④⑤ 最新披露财报
        ind = self.latest_indicator(code, date)
        if ind is None:
            return False
        ocf = ind.get('ocf_to_operating_profit')
        gross = ind.get('gross_profit_margin')
        net = ind.get('net_profit_margin')
        rev_yoy = ind.get('inc_revenue_year_on_year')
        np_yoy = ind.get('inc_net_profit_year_on_year')
        if ocf is None or gross is None or net is None or rev_yoy is None or np_yoy is None:
            return False
        if not (ocf > TH_OCF):
            return False
        if not (gross > TH_GROSS and net > TH_NET):
            return False
        if not (rev_yoy > TH_REV_YOY and np_yoy > TH_NP_YOY):
            return False
        return True

    def eligible(self, date, codes: Optional[List[str]] = None) -> List[str]:
        """date 日合格票集合（codes 为候选子集，None=全部已加载）"""
        codes = codes or list(self._pe_pb.keys())
        return [c for c in codes if self.is_eligible(c, date)]

    # ---------- 诊断 ----------
    def pool_history(self, start: str = '2024-03-29', end: str = '2026-08-27',
                     freq: str = 'ME', codes: Optional[List[str]] = None) -> pd.DataFrame:
        """月度抽样池成员（诊断用）：返回 DataFrame[date, size, members]"""
        rows = []
        for d in pd.date_range(start, end, freq=freq):
            elig = self.eligible(d, codes=codes)
            rows.append({'date': d.date(), 'size': len(elig), 'members': ','.join(sorted(elig))})
        return pd.DataFrame(rows)


if __name__ == '__main__':
    sel = WangwenSelector()
    print(f"本地估值 {len(sel._pe_pb)} 只，在线财报期表 {len(sel._ind_series)} 只\n")
    print(sel.pool_history().to_string(index=False))
    last = pd.Timestamp('2026-08-27')
    elig = sel.eligible(last)
    print(f"\n[对照] {last.date()} 当日池: {len(elig)} 只")
    print(','.join(sorted(elig)) if elig else '-')
