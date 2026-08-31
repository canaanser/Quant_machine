# -*- coding: utf-8 -*-
"""
档案系统验证（2026-08-30 老板：股票=人，数据=档案）
====================================================
虚拟组装：kline + fundamentals + tags + meta 四类档案组装成 StockProfile。
只读验证，不落盘。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.profile import assemble, assemble_one, StockProfile
from core.profile.readers import KlineReader, FundamentalsReader, TagsReader, MetaReader

DATE = '2026-08-28'   # 最近一个交易日（与标签数据对齐）
CODES = ['000063', '000657', '600941']  # 中兴 / 中钨高新 / 中国移动

print('=' * 70)
print(f'档案系统验证 date={DATE}')
print('=' * 70)

# 1) 单票组装（全部四类档案）
p = assemble_one('000063', date=DATE)
print(f'\n[1] assemble_one(000063) -> {p}')
print(f'    name        = {p.name()}')
print(f'    tags        = {p.fields.get("tags")}')
print(f'    realtime    = {p.fields.get("fundamentals", {}).get("realtime")}')
ind = p.fields.get('fundamentals', {}).get('latest_indicator') or {}
print(f'    indicator   = statDate={ind.get("statDate")} pubDate={ind.get("pubDate")} '
      f'np_yoy={ind.get("inc_net_profit_year_on_year")}')
k = p.fields.get('kline') or {}
print(f'    kline       = {len(k.get("price", []))} bars, last_close={p.latest_close()}')

# 2) 批量组装
print(f'\n[2] assemble 3 只 ->')
profiles = assemble(CODES, date=DATE)
for code, prof in profiles.items():
    ind = prof.fields.get('fundamentals', {}).get('latest_indicator') or {}
    rt = prof.fields.get('fundamentals', {}).get('realtime') or {}
    tags = prof.fields.get('tags') or {}
    print(f'    {code} {prof.name():8s} tags={tags} pe={rt.get("pe_ttm"):.1f} '
          f'np_yoy={ind.get("inc_net_profit_year_on_year")}')

# 3) 便捷查询方法
print(f'\n[3] 便捷查询 000063')
p3 = profiles['000063']
print(f'    p3.tag("oscillation")     = {p3.tag("oscillation")}')
print(f'    p3.tag("marketcap")       = {p3.tag("marketcap")}')
print(f'    p3.indicator("inc_net_profit_year_on_year") = {p3.indicator("inc_net_profit_year_on_year")}')
print(f'    p3.indicator("gross_profit_margin")          = {p3.indicator("gross_profit_margin")}')
print(f'    p3.realtime("total_mv")   = {p3.realtime("total_mv"):.2e}')
print(f'    p3.latest_close()         = {p3.latest_close()}')

# 4) 无日期：全量 K 线
print(f'\n[4] 全量档案（date=None）')
p4 = assemble_one('000063', date=None, fields=['kline', 'meta'])
print(f'    {p4} kline_bars={len(p4.fields.get("kline", {}).get("price", []))} name={p4.name()}')

# 5) 读取器独立性（干湿分离：单 reader 可独立用）
print(f'\n[5] 读取器独立可用')
r = MetaReader()
print(f'    MetaReader.read("000063") = {r.read("000063")}')
r2 = TagsReader(tag_names=['oscillation'])
print(f'    TagsReader(tag_names=["oscillation"]).read("000063", {DATE}) = {r2.read("000063", date=DATE)}')

print('\n' + '=' * 70)
print('全部通过 ✅  档案系统 = 虚拟组装，未落盘任何数据')
print('=' * 70)
