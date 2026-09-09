# 职责: 股票静态画像/基本面元数据(读); 不存动态因子/策略结果
# -*- coding: utf-8 -*-
"""
股票档案·虚拟组装（2026-08-30 老板：股票=人，数据=档案）
========================================================
干湿分离：
  - 功能 = 本文件（组装逻辑）
  - 模块 = readers/（每类档案一个读取器，互不依赖）
  - 数据 = data/ 下各档案文件（互不合并）
  - 产物 = 虚拟组装结果（运行时生成，不落盘）

StockProfile = 一只股票在某日的"全部档案"逻辑视图。
assemble()  = 多只股票 × 多类档案的批量组装入口。
"""
from typing import Dict, List, Optional

from .readers import KlineReader, FundamentalsReader, TagsReader, MetaReader

#: 档案名 -> 默认读取器（单例，惰性实例化）
_DEFAULT_READERS = {
    'kline': KlineReader,
    'fundamentals': FundamentalsReader,
    'tags': TagsReader,
    'meta': MetaReader,
}
_reader_instances: Dict[str, object] = {}


def _get_reader(name: str):
    if name not in _reader_instances:
        _reader_instances[name] = _DEFAULT_READERS[name]()
    return _reader_instances[name]


class StockProfile:
    """一只股票的档案视图（虚拟组装结果，不落盘）"""

    def __init__(self, code: str):
        self.code = str(code).zfill(6)
        #: {档案名: 该档案数据}；缺的档案不出现
        self.fields: Dict[str, object] = {}

    def add(self, name: str, data) -> 'StockProfile':
        if data is not None:
            self.fields[name] = data
        return self

    def get(self, name: str, default=None):
        return self.fields.get(name, default)

    def __getattr__(self, item):
        # 便捷访问：profile.kline / profile.fundamentals / profile.tags / profile.meta
        if item in _DEFAULT_READERS:
            return self.fields.get(item)
        raise AttributeError(item)

    def __repr__(self):
        return f"<StockProfile {self.code} fields={list(self.fields)}>"

    # ---------- 便捷查询 ----------
    def name(self) -> Optional[str]:
        m = self.fields.get('meta')
        return m.get('name') if m else None

    def tag(self, tag_name: str):
        """取某标签在某日的值（tags 档案是 {tag: value}）"""
        t = self.fields.get('tags')
        return t.get(tag_name) if t else None

    def indicator(self, key: str, default=None):
        """取最新一期财报指标（fundamentals.latest_indicator[key]）"""
        f = self.fields.get('fundamentals')
        ind = f.get('latest_indicator') if f else None
        return ind.get(key, default) if ind else default

    def realtime(self, key: str, default=None):
        """取 T 日实时估值（fundamentals.realtime[key]）"""
        f = self.fields.get('fundamentals')
        rt = f.get('realtime') if f else None
        return rt.get(key, default) if rt else default

    def latest_close(self, date=None) -> Optional[float]:
        """取 K 线里 date（默认最后一天）收盘价"""
        k = self.fields.get('kline')
        if not k:
            return None
        s = k.get('price')
        if s is None or len(s) == 0:
            return None
        if date is None:
            return float(s.iloc[-1])
        before = s[s.index <= date]
        if len(before) == 0:
            return None
        return float(before.iloc[-1])


def assemble(codes: List[str], date=None, fields: Optional[List[str]] = None,
             readers: Optional[Dict[str, object]] = None) -> Dict[str, StockProfile]:
    """批量组装股票档案（虚拟，不落盘）。

    参数:
      codes   : 股票代码列表（自动 zfill(6)）
      date    : 档案日期（None = 全量，如 kline 全量行情）
      fields  : 要组装的档案名列表（None = 全部：kline/fundamentals/tags/meta）
      readers : 自定义读取器 {档案名: reader 实例}（测试/换数据源用）
    返回:
      {code: StockProfile}
    """
    if fields is None:
        fields = list(_DEFAULT_READERS.keys())
    rs = {k: (readers[k] if readers and k in readers else _get_reader(k)) for k in fields}
    out: Dict[str, StockProfile] = {}
    for code in codes:
        p = StockProfile(code)
        for fname in fields:
            try:
                data = rs[fname].read(code, date=date)
            except Exception:
                data = None
            if data:
                p.add(fname, data)
        out[p.code] = p
    return out


def assemble_one(code: str, date=None, fields: Optional[List[str]] = None,
                 readers: Optional[Dict[str, object]] = None) -> StockProfile:
    """单只股票档案组装"""
    return assemble([code], date=date, fields=fields, readers=readers)[str(code).zfill(6)]
