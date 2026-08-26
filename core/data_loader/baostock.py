# -*- coding: utf-8 -*-
"""
baostock 数据源
（2026-08-26 小二陈：从 core/data_loader.py 拆出，接口不变）
"""
import pandas as pd
from config import START_DATE, END_DATE
from ..data_structures import metadata

def fetch_data_baostock(stock_list, start=START_DATE, end=END_DATE) -> metadata:
    import baostock as bs
    lg = bs.login()
    print('BaoStock login respond error_code:' + lg.error_code)
    print('BaoStock login respond error_msg:' + lg.error_msg)
    all_close = {}
    fields = "date,code,open,high,low,close,volume,amount"
    for code in stock_list:
        try:
            code_str = str(code).zfill(6)
            if code_str.startswith(('6', '5')):
                bs_code = f"sh.{code_str}"
            else:
                bs_code = f"sz.{code_str}"
            rs = bs.query_history_k_data_plus(bs_code, fields,
                                              start_date=start, end_date=end,
                                              frequency="d", adjustflag="3")
            data_list = []
            while (rs.error_code == '0') and rs.next():
                data_list.append(rs.get_row_data())
            if not data_list:
                print(f"警告: {code} 未获取到数据")
                continue
            df = pd.DataFrame(data_list, columns=rs.fields)
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            all_close[code] = df['close']
        except Exception as e:
            print(f"获取 {code} 失败: {e}")
            continue
    bs.logout()
    price_df = pd.DataFrame(all_close)
    if price_df.empty:
        print("错误: 未获取到任何股票数据")
        return metadata(price=pd.DataFrame(), benchmark=pd.Series())
    benchmark = price_df.mean(axis=1)
    benchmark.name = 'EqualWeight'
    return metadata(price=price_df, benchmark=benchmark, open_price=pd.DataFrame()).align()


# 拉取过的 K 线缓存到 data/cache/stockdb/，二次扫描直接读缓存（零 HTTP 请求），
# 仅对缓存缺失的年份增量拉取。避免"每跑一次重拉一遍"。
