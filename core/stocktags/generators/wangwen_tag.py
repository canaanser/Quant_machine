# -*- coding: utf-8 -*-
"""
王文五标签生成器（2026-08-30 标签系统）
========================================
与 selection/WangwenSelector（筛选器/决策层）完全分离——本模块只做"描述层"：

  筛选器 WangwenSelector      → "当日可买名单"（买/不买，决策）
  标签   WangwenTagGenerator  → "符合几项/弱项"标签（描述）

原则：互不引用、互不依赖、阈值各自定义（与筛选器阈值一致但独立持有，
避免两模块耦合）。各自独立消费同一份财报数据（data/info/fundamentals/reports/）。

标签值：
  value = 符合几项（'4'/'3'/'2'/'1'/'0'）——王文五 ①②④⑤ 四项绝对阈值
  weak  = 不符合的项（逗号分隔，如 '估值,现金流'）——附加列
  valid_from/valid_to = 该期财报披露日 pubDate ~ 下期披露日（随时间滚动）
"""
import glob
import json
import os
from typing import List, Optional

import pandas as pd

from config import PROJECT_ROOT, FUNDAMENTALS_DAILY_DIR, FUNDAMENTALS_REPORTS_DIR
from ..base import BaseTagGenerator

# ===== 王文五绝对阈值（与 selection/wangwen.py 一致，但独立持有——避免模块耦合）=====
TH_PE_MAX = 30.0
TH_PB_MAX = 5.0
TH_OCF = 0.5
TH_GROSS = 20.0
TH_NET = 0.0
TH_REV_YOY = 0.0
TH_NP_YOY = 0.0


class WangwenTagGenerator(BaseTagGenerator):
    """王文五标准标签：符合几项 + 弱项（描述层，独立于筛选器）"""

    name = "wangwen_tag"
    version = "v1"
    value_domain = ['4', '3', '2', '1', '0']

    #: 附加列（在标准 TAG_COLUMNS 之外的扩展）
    extra_columns = ['weak']

    def _load_indicator(self):
        """读全部财报 indicator 期表：code -> [(pubDate, dict)]（按 pubDate 排序）"""
        ind_series = {}
        reports_dir = os.path.join(PROJECT_ROOT, FUNDAMENTALS_REPORTS_DIR)
        for f in glob.glob(os.path.join(reports_dir, '*.csv')):
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
                    ind_series[code] = rows
            except Exception:
                continue
        return ind_series

    def _realtime_pe_pb(self, code: str, date) -> tuple:
        """T 日（或前最近）实时 pe_ttm/pb（本地每日估值）"""
        f = os.path.join(PROJECT_ROOT, FUNDAMENTALS_DAILY_DIR, f'{code}.csv')
        if not os.path.exists(f):
            return None, None
        try:
            df = pd.read_csv(f)
            df['date'] = pd.to_datetime(df['date'])
            d = pd.Timestamp(date)
            sub = df[df['date'] <= d]
            if len(sub) == 0:
                return None, None
            row = sub.iloc[-1]
            return float(row['pe_ttm']), float(row['pb'])
        except Exception:
            return None, None

    def generate(self, codes: Optional[List[str]] = None,
                 start: Optional[str] = None,
                 end: Optional[str] = None) -> pd.DataFrame:
        ind_series = self._load_indicator()
        all_codes = list(ind_series.keys())
        if codes is not None:
            all_codes = [c for c in all_codes if c in set(codes)]
        rows = []
        for code in all_codes:
            series = ind_series[code]
            for idx, (pub, ind) in enumerate(series):
                pe, pb = self._realtime_pe_pb(code, pub)
                ok_val = (pe is not None and 0 < pe < TH_PE_MAX
                          and pb is not None and pb < TH_PB_MAX)
                ocf = ind.get('ocf_to_operating_profit')
                gross = ind.get('gross_profit_margin')
                net = ind.get('net_profit_margin')
                rev = ind.get('inc_revenue_year_on_year')
                np_yoy = ind.get('inc_net_profit_year_on_year')
                ok_cf = ocf is not None and ocf > TH_OCF
                ok_q = (gross is not None and net is not None
                        and gross > TH_GROSS and net > TH_NET)
                ok_g = (rev is not None and np_yoy is not None
                        and rev > TH_REV_YOY and np_yoy > TH_NP_YOY)
                checks = {'估值': ok_val, '现金流': ok_cf, '质量': ok_q, '成长': ok_g}
                passed = sum(1 for v in checks.values() if v)
                weak = ','.join(k for k, v in checks.items() if not v)
                valid_to = series[idx + 1][0] if idx + 1 < len(series) else None
                rows.append({
                    'code': code,
                    'valid_from': pub,
                    'valid_to': valid_to,
                    'value': str(passed),
                    'version': self.version,
                    'weak': weak,
                })
        df = self.normalize(pd.DataFrame(rows))
        return df
