# -*- coding: utf-8 -*-
"""
数据加载层（2026-08-26 小二陈：从 core/data_loader.py 拆分为包，接口不变）
统一入口 load_data 在此保留；各数据源独立文件：
  base.py（缓存工具）/ yfinance / akshare / baostock / freestockdb（含 HTTP 适配）
"""

from ..data_structures import metadata
from config import START_DATE, END_DATE
from .base import (_STOCKDB_CACHE_DIR, _cache_path, _load_stockdb_cache, _save_stockdb_cache)
from .yfinance import fetch_data_yfinance
from .akshare import fetch_data_akshare
from .baostock import fetch_data_baostock
from .freestockdb import fetch_data_stockdb_http, fetch_data_freestockdb


def load_data(source='yfinance', **kwargs) -> metadata:
    if source == 'yfinance':
        return fetch_data_yfinance(**kwargs)
    elif source == 'akshare':
        if 'tickers' in kwargs:
            kwargs['stock_list'] = kwargs.pop('tickers')
        return fetch_data_akshare(**kwargs)
    elif source == 'baostock':
        if 'tickers' in kwargs:
            kwargs['stock_list'] = kwargs.pop('tickers')
        return fetch_data_baostock(**kwargs)
    elif source == 'freestockdb':
        if 'tickers' in kwargs:
            kwargs['stock_list'] = kwargs.pop('tickers')
        return fetch_data_freestockdb(**kwargs)
    elif source == 'stockdb_http':
        if 'tickers' in kwargs:
            kwargs['stock_list'] = kwargs.pop('tickers')
        return fetch_data_stockdb_http(**kwargs)
    else:
        raise ValueError("source 只支持 'yfinance', 'akshare', 'baostock', 'freestockdb' 或 'stockdb_http'")


__all__ = [
    'load_data', 'metadata',
    'fetch_data_yfinance', 'fetch_data_akshare', 'fetch_data_baostock',
    'fetch_data_freestockdb', 'fetch_data_stockdb_http',
]
