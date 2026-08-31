# -*- coding: utf-8 -*-
"""
标签消费引擎（2026-08-30 老板：标签归类系统）
==============================================
查询/组装/层级/回填的统一入口：

  tag_at(code, date, tag)         某票某日某标签值
  filter(codes, date, **tags)     多标签 AND 组装（过滤）
  assemble(date, tags, op)        自由组装（AND/OR）
  hierarchy(tag_a, tag_b, date)   层级：A 分组内再按 B 细分
  backfill(tag, overwrite)        回填/重算历史标签

数据读取：
  - 生成器 produce() 结果落盘到 data/info/tags/data/{name}_{version}.csv
  - 引擎读落盘文件（快）；未落盘则现场生成（兜底）
"""
import os
from typing import Dict, List, Optional

import pandas as pd

from config import PROJECT_ROOT, TAGS_DATA_DIR
from .registry import get, list_tags
from .base import TAG_COLUMNS


# ============ 数据读写 ============

def _data_path(tag: str, version: str) -> str:
    return os.path.join(TAGS_DATA_DIR, f"{tag}_{version}.csv")


def load(tag: str) -> pd.DataFrame:
    """加载标签长表（落盘优先，未落盘现场生成）"""
    gen = get(tag)
    if gen is None:
        raise KeyError(f"未注册标签: {tag}，可用: {[t['name'] for t in list_tags()]}")
    p = _data_path(tag, gen.version)
    if os.path.exists(p):
        df = pd.read_csv(p, dtype={'code': str})
        df['code'] = df['code'].str.zfill(6)
        df['valid_from'] = pd.to_datetime(df['valid_from'])
        df['valid_to'] = pd.to_datetime(df['valid_to'])
        df['value'] = df['value'].astype(str)   # 统一字符串（避免 int '4' vs str '4' 歧义）
        return df
    return gen.generate()


def produce(tag: str, codes: Optional[List[str]] = None,
            start: Optional[str] = None, end: Optional[str] = None,
            overwrite: bool = True) -> str:
    """生成并落盘标签数据（backfill 底层）"""
    gen = get(tag)
    if gen is None:
        raise KeyError(f"未注册标签: {tag}")
    p = _data_path(tag, gen.version)
    if os.path.exists(p) and not overwrite:
        return p
    df = gen.generate(codes=codes, start=start, end=end)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    df.to_csv(p, index=False, encoding='utf-8')
    return p


def backfill(tag: str, codes: Optional[List[str]] = None,
             start: Optional[str] = None, end: Optional[str] = None,
             overwrite: bool = True) -> str:
    """回填/重算历史标签（规则迭代后调用）"""
    return produce(tag, codes=codes, start=start, end=end, overwrite=overwrite)


# ============ 查询 ============

def tag_at(code: str, date, tag: str) -> Optional[str]:
    """某票在 date 日的标签值（None=该日无标签/不在有效期内）"""
    df = load(tag)
    code = str(code).zfill(6)
    d = pd.Timestamp(date)
    m = (df['code'] == code) & (df['valid_from'] <= d) & (
        df['valid_to'].isna() | (df['valid_to'] >= d))
    hits = df[m]
    if len(hits) == 0:
        return None
    return hits.iloc[-1]['value']


def _codes_at_date(df: pd.DataFrame, date, tag_value: str) -> set:
    d = pd.Timestamp(date)
    m = (df['value'] == tag_value) & (df['valid_from'] <= d) & (
        df['valid_to'].isna() | (df['valid_to'] >= d))
    return set(df[m]['code'])


# ============ 组装 ============

def filter(codes: Optional[List[str]], date, **tags) -> List[str]:
    """多标签 AND 过滤：同时满足所有 tag=value 条件的股票
    例：filter(None, '2026-08-28', oscillation='震荡票', wangwen='合格')
    """
    result = set(codes) if codes is not None else None
    for tag, value in tags.items():
        df = load(tag)
        s = _codes_at_date(df, date, str(value))
        result = s if result is None else (result & s)
        if not result:
            return []
    return sorted(result)


def assemble(date, tags: Dict[str, str], op: str = 'AND',
             codes: Optional[List[str]] = None) -> List[str]:
    """自由组装：op='AND' 全满足 / op='OR' 任一满足"""
    sets = []
    for tag, value in tags.items():
        sets.append(_codes_at_date(load(tag), date, str(value)))
    if op.upper() == 'OR':
        union = set().union(*sets) if sets else set()
        result = union
    else:
        result = set.intersection(*sets) if sets else set()
    if codes is not None:
        result = result & set(codes)
    return sorted(result)


def hierarchy(tag_a: str, tag_b: str, date, value_a: Optional[str] = None) -> Dict[str, List[str]]:
    """层级组装：A 标签分组，组内再按 B 细分
    例：hierarchy('oscillation','industry','2026-08-28')
        → {'震荡票': {'通信': [codes], '公用': [...]}, '趋势票': {...}}
    """
    df_a = load(tag_a)
    df_b = load(tag_b)
    d = pd.Timestamp(date)
    a_map = {}  # code -> a_value
    for _, r in df_a.iterrows():
        if r['valid_from'] <= d and (pd.isna(r['valid_to']) or r['valid_to'] >= d):
            a_map[r['code']] = r['value']
    b_map = {}
    for _, r in df_b.iterrows():
        if r['valid_from'] <= d and (pd.isna(r['valid_to']) or r['valid_to'] >= d):
            b_map[r['code']] = r['value']
    out = {}
    for code, av in a_map.items():
        if value_a is not None and av != value_a:
            continue
        bv = b_map.get(code, '未知')
        out.setdefault(av, {}).setdefault(bv, []).append(code)
    for av in out:
        for bv in out[av]:
            out[av][bv].sort()
    return out
