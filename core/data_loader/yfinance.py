# -*- coding: utf-8 -*-
"""
yfinance 数据源
（2026-08-26 小二陈：从 core/data_loader.py 拆出，接口不变）
"""
import pandas as pd
from config import START_DATE, END_DATE
from ..data_structures import metadata

def fetch_data_yfinance(tickers, start=START_DATE, end=END_DATE) -> metadata:
    # 延迟导入：避免在未安装 yfinance 的环境（如 WSL/Linux）import 本模块失败
    import yfinance as yf
    if isinstance(tickers, str):
        tickers = [tickers]
    data = yf.download(tickers, start=start, end=end, progress=False)
    price_df = data['Adj Close']
    if isinstance(price_df, pd.Series):
        price_df = price_df.to_frame(tickers[0])
    benchmark = yf.download('SPY', start=start, end=end, progress=False)['Adj Close']
    benchmark.name = 'SPY'
    return metadata(price=price_df, benchmark=benchmark, open_price=pd.DataFrame()).align()
