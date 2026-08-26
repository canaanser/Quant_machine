# -*- coding: utf-8 -*-
"""
akshare 数据源
（2026-08-26 小二陈：从 core/data_loader.py 拆出，接口不变）
"""
from core.logger import get_logger

logger = get_logger(__name__)

import pandas as pd
from config import START_DATE, END_DATE
from ..data_structures import metadata

def fetch_data_akshare(stock_list, benchmark_code="sh000300", start=START_DATE, end=END_DATE) -> metadata:
    import akshare as ak
    all_close = {}
    start_str = start.replace('-', '')
    end_str = end.replace('-', '')
    for code in stock_list:
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                    start_date=start_str, end_date=end_str)
            if df is not None and not df.empty:
                df['日期'] = pd.to_datetime(df['日期'])
                df = df.set_index('日期')
                all_close[code] = df['收盘']
        except Exception as e:
            logger.error(f"获取 {code} 失败: {e}")
            continue
    price_df = pd.DataFrame(all_close)
    try:
        index_df = ak.index_zh_a_hist(symbol=benchmark_code, period="daily",
                                      start_date=start_str, end_date=end_str)
        if index_df is not None and not index_df.empty:
            index_df['日期'] = pd.to_datetime(index_df['日期'])
            index_df = index_df.set_index('日期')
            benchmark = index_df['收盘']
            benchmark.name = benchmark_code
        else:
            raise Exception("获取基准数据为空")
    except Exception as e:
        logger.error(f"获取基准失败: {e}, 使用等权平均替代")
        benchmark = price_df.mean(axis=1)
        benchmark.name = 'EqualWeight'
    return metadata(price=price_df, benchmark=benchmark, open_price=pd.DataFrame()).align()
