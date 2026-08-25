import pandas as pd
import yfinance as yf
import akshare as ak
import baostock as bs
from config import START_DATE, END_DATE
from .data_structures import metadata

def fetch_data_yfinance(tickers, start=START_DATE, end=END_DATE) -> metadata:
    if isinstance(tickers, str):
        tickers = [tickers]
    data = yf.download(tickers, start=start, end=end, progress=False)
    price_df = data['Adj Close']
    if isinstance(price_df, pd.Series):
        price_df = price_df.to_frame(tickers[0])
    benchmark = yf.download('SPY', start=start, end=end, progress=False)['Adj Close']
    benchmark.name = 'SPY'
    return metadata(price=price_df, benchmark=benchmark).align()

def fetch_data_akshare(stock_list, benchmark_code="sh000300", start=START_DATE, end=END_DATE) -> metadata:
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
            print(f"获取 {code} 失败: {e}")
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
        print(f"获取基准失败: {e}, 使用等权平均替代")
        benchmark = price_df.mean(axis=1)
        benchmark.name = 'EqualWeight'
    return metadata(price=price_df, benchmark=benchmark).align()

def fetch_data_baostock(stock_list, start=START_DATE, end=END_DATE) -> metadata:
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
    return metadata(price=price_df, benchmark=benchmark).align()

def fetch_data_freestockdb(
    stock_list,
    start=START_DATE,
    end=END_DATE,
    frequency="1d",
    fq="qfq"
) -> metadata:
    """
    从 free-stockdb 本地数据引擎获取数据（使用 Python SDK）
    需要先运行 pybao/安装.py 安装依赖
    """
    import sys as _sys
    import os as _os
    project_root = _os.path.dirname(_os.path.dirname(__file__))
    pybao_path = _os.path.join(project_root, 'pybao')
    if pybao_path not in _sys.path:
        _sys.path.insert(0, pybao_path)
    
    try:
        from stock_sdk import rd, init
    except ImportError:
        print("❌ 无法导入 free-stockdb SDK")
        print("   请确保:")
        print("   1. 将 free-stockdb 发行包中的 pybao 文件夹复制到项目根目录")
        print("   2. 运行 python pybao/安装.py 安装依赖")
        raise
    
    # 初始化 SDK 连接
    try:
        init(host="127.0.0.1", port=7899, warm=False)
        print("🔗 已连接到 free-stockdb 本地服务: 127.0.0.1:7899")
    except Exception as e:
        print(f"❌ 连接 free-stockdb 服务失败: {e}")
        print("   请确保 stockdb 服务已启动")
        raise
    
    # 日期格式转换：YYYY-MM-DD → YYYYMMDD
    start_clean = start.replace('-', '')
    end_clean = end.replace('-', '')
    
    # 判断是否为批量查询
    is_batch = len(stock_list) > 1
    
    try:
        # 调用 SDK 的 get_data 接口
        result = rd.get_data(
            code=stock_list if is_batch else stock_list[0],
            start=start_clean,
            end=end_clean,
            frequency=frequency,
            fq=fq,
            as_df=True
        )
        
        if result is None or result.empty:
            print("❌ 未获取到任何数据")
            return metadata(price=pd.DataFrame(), benchmark=pd.Series())
        
        # ---------- 日期列转换 ----------
        if 'date' in result.columns:
            # 尝试多种日期格式
            result['date'] = pd.to_datetime(result['date'].astype(str), format='%Y%m%d', errors='coerce')
            if result['date'].isna().any():
                result['date'] = pd.to_datetime(result['date'].astype(str), format='%Y%m%d%H%M%S', errors='coerce')
        else:
            print("⚠️ 返回数据中没有 'date' 列")
            return metadata(price=pd.DataFrame(), benchmark=pd.Series())
        
        result = result.dropna(subset=['date'])
        
        if result.empty:
            print("❌ 日期转换后数据为空")
            return metadata(price=pd.DataFrame(), benchmark=pd.Series())
        
        # ---------- 提取股票信息（名称） ----------
        if is_batch:
            # 批量查询：从数据中提取股票名称
            info_df = result.drop_duplicates(subset=['code'])[['code', 'name']].set_index('code')
            # 透视价格
            price_df = result.pivot_table(index='date', columns='code', values='close')
            # ---------- 构建开盘价数据 ----------
            if 'open' in result.columns:
                open_price_df = result.pivot_table(index='date', columns='code', values='open')
                print(f"📊 开盘价数据已加载，形状: {open_price_df.shape}")
            else:
                # 如果没有 open 列，用收盘价替代（回退）
                open_price_df = price_df.copy()
                print("⚠️ 数据中无 'open' 列，开盘价将使用收盘价替代")
            # 确保日期索引与 price_df 一致
            open_price_df = open_price_df.loc[price_df.index]
            # 同时构建开盘价数据
            if 'open' in result.columns:
                open_price_df = result.pivot_table(index='date', columns='code', values='open')
            else:
                open_price_df = price_df  # 备用：用收盘价替代
            print(f"📊 批量数据透视后: {price_df.shape}")
        else:
            # 单只股票
            code = stock_list[0]
            # 获取名称
            name = result['name'].iloc[0] if 'name' in result.columns else code
            info_df = pd.DataFrame({'code': [code], 'name': [name]}).set_index('code')
            # 设置日期索引
            result = result.set_index('date')
            price_df = result[['close']]
            price_df.columns = [code]
            print(f"📊 单只数据处理后: {price_df.shape}")
        
        if price_df.empty:
            print("❌ 价格数据为空")
            return metadata(price=pd.DataFrame(), benchmark=pd.Series())
        
        # 删除全为 NaN 的列
        price_df = price_df.dropna(axis=1, how='all')
        
        # 确保数值类型
        for col in price_df.columns:
            price_df[col] = pd.to_numeric(price_df[col], errors='coerce')
        
        # 构建基准（等权平均）
        benchmark = price_df.mean(axis=1)
        benchmark.name = 'EqualWeight'
        
        print(f"✅ 成功加载 {len(price_df.columns)} 只股票，{len(price_df)} 个交易日")
        print(f"📅 日期范围: {price_df.index.min()} 至 {price_df.index.max()}")
        if not info_df.empty:
            print(f"📋 股票信息: {info_df.to_dict(orient='index')}")
        
        return metadata(price=price_df, benchmark=benchmark, info=info_df).align()
        
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return metadata(price=pd.DataFrame(), benchmark=pd.Series())

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
    else:
        raise ValueError("source 只支持 'yfinance', 'akshare', 'baostock' 或 'freestockdb'")
