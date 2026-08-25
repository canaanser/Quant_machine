import pandas as pd
from pathlib import Path
from config import START_DATE, END_DATE
from .data_structures import metadata


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
    return metadata(price=price_df, benchmark=benchmark, open_price=pd.DataFrame()).align()


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


# ===== stockdb HTTP 数据本地缓存（2026-08-26 小二陈） =====
# 拉取过的 K 线缓存到 data/cache/stockdb/，二次扫描直接读缓存（零 HTTP 请求），
# 仅对缓存缺失的年份增量拉取。避免"每跑一次重拉一遍"。
_STOCKDB_CACHE_DIR = Path(__file__).parent.parent / "data" / "cache" / "stockdb"


def _cache_path(symbol: str, frequency: str):
    freq_tag = "1d" if frequency in (None, "1d", "1D") else str(frequency)
    return _STOCKDB_CACHE_DIR / f"{symbol}_{freq_tag}.csv"


def _load_stockdb_cache(symbol: str, frequency: str):
    """读缓存，返回 date 索引的 DataFrame，无缓存/损坏返回 None"""
    p = _cache_path(symbol, frequency)
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p)
        if 'date' not in df.columns or df.empty:
            return None
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date']).set_index('date').sort_index()
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception:
        return None


def _save_stockdb_cache(symbol: str, frequency: str, df) -> None:
    """写缓存（覆盖合并后的全量结果）"""
    try:
        _STOCKDB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(_cache_path(symbol, frequency), encoding='utf-8')
    except Exception as e:
        print(f"⚠️ 缓存写入失败 {symbol}: {e}")


def fetch_data_stockdb_http(
    stock_list,
    start=START_DATE,
    end=END_DATE,
    frequency="1d",
    fq="qfq",
    host="127.0.0.1",
    port=7899,
) -> metadata:
    """
    从 free-stockdb 本地数据引擎获取数据（HTTP 协议版 + 本地缓存）

    与 fetch_data_freestockdb 输出契约完全一致（返回 metadata），
    不依赖 Windows 二进制 stockdb.pyd，可在 WSL/Linux 环境直接使用。

    性能优化（2026-08-26 小二陈）：
      拉取过的 K 线缓存到 data/cache/stockdb/{code}_{freq}.csv，
      二次扫描直接读缓存，仅对缓存缺失的年份做增量 HTTP 拉取。
    """
    import json as _json
    import urllib.request as _ur
    import urllib.parse as _up
    from pathlib import Path

    # 本地服务不走代理：显式禁用 ProxyHandler，避免 http_proxy 环境变量导致 502
    _opener = _ur.build_opener(_ur.ProxyHandler({}))

    table = "分钟k" if frequency in ("1m", "5m", "15m", "30m", "60m") else "日k"
    start_year = int(str(start)[:4])
    end_year = int(str(end)[:4])
    is_batch = len(stock_list) > 1

    all_frames = {}
    for code in stock_list:
        code = str(code).zfill(6)

        # 1. 读本地缓存
        cached_df = _load_stockdb_cache(code, frequency)

        # 2. 确定需要拉取的年份（增量：只拉缓存未覆盖的）
        need_years = list(range(start_year, end_year + 1))
        if cached_df is not None and not cached_df.empty:
            cached_last = cached_df.index.max().year
            need_years = [y for y in need_years if y > cached_last]

        # 3. 拉取缺失年份
        rows_all = []
        for year in need_years:
            expr = f"{table}:{code}:{year}*"
            url = f"http://{host}:{port}/?cmd=get&t={_up.quote(expr)}"
            try:
                with _opener.open(url, timeout=30) as resp:
                    raw = _json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print(f"⚠️ HTTP 获取 {code} {year} 失败: {e}")
                continue
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, (list, tuple)) and len(item) > 1 and isinstance(item[1], dict):
                        rows_all.append(item[1])

        # 4. 合并缓存 + 新拉数据
        df = None
        if cached_df is not None and not cached_df.empty:
            df = cached_df.copy()
        if rows_all:
            new_df = pd.DataFrame(rows_all)
            if 'date' in new_df.columns:
                new_df['date'] = pd.to_datetime(new_df['date'].astype(str), format='%Y%m%d', errors='coerce')
                new_df = new_df.dropna(subset=['date']).set_index('date').sort_index()
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    if col in new_df.columns:
                        new_df[col] = pd.to_numeric(new_df[col], errors='coerce')
                if df is not None:
                    df = pd.concat([df, new_df])
                    df = df[~df.index.duplicated(keep='last')].sort_index()
                else:
                    df = new_df

        if df is None or df.empty:
            print(f"⚠️ {code} 未获取到数据（HTTP）")
            continue

        # 5. 写缓存（合并后的全量）
        _save_stockdb_cache(code, frequency, df)

        # 6. 按请求区间过滤
        df = df.loc[str(start):str(end)]
        if df.empty:
            print(f"⚠️ {code} 在区间 {start}~{end} 内无数据")
            continue
        all_frames[code] = df

    if not all_frames:
        print("❌ HTTP 数据加载失败：未获取到任何股票数据")
        return metadata(price=pd.DataFrame(), benchmark=pd.Series())

    # 统一索引（取各股票日期的并集再按交易日排序）
    common_idx = sorted(set().union(*[set(df.index) for df in all_frames.values()]))

    def _build_matrix(col_name, default=0.0):
        mat = pd.DataFrame(index=common_idx)
        for code, df in all_frames.items():
            if col_name in df.columns:
                mat[code] = df[col_name]
            else:
                mat[code] = default
        return mat

    price_df = _build_matrix('close')
    open_price_df = _build_matrix('open')
    high_price_df = _build_matrix('high')
    low_price_df = _build_matrix('low')
    volume_df = _build_matrix('volume')

    info_records = []
    for code, df in all_frames.items():
        name = df['name'].iloc[0] if 'name' in df.columns else code
        info_records.append({'code': code, 'name': name})
    info_df = pd.DataFrame(info_records).set_index('code')

    # 基准：等权平均（与 SDK 版本行为一致）
    benchmark = price_df.mean(axis=1)
    benchmark.name = 'EqualWeight'

    print(f"✅ HTTP 成功加载 {len(price_df.columns)} 只股票，{len(price_df)} 个交易日（缓存: {'命中' if cached_df is not None else '首次'}）")
    print(f"📅 日期范围: {price_df.index.min()} 至 {price_df.index.max()}")
    if fq != 'none':
        print("ℹ️ 提示: HTTP 接口返回原始价，未做复权折算（fq 参数仅兼容保留）")

    return metadata(
        price=price_df,
        benchmark=benchmark,
        open_price=open_price_df,
        high_price=high_price_df,
        low_price=low_price_df,
        volume=volume_df,
        info=info_df
    ).align()


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
        # 非 Windows 环境（如 WSL/Linux）没有 stockdb.pyd，自动回退 HTTP 协议
        print("⚠️ free-stockdb SDK 不可用（当前非 Windows 环境），自动回退 HTTP 协议...")
        return fetch_data_stockdb_http(
            stock_list, start=start, end=end, frequency=frequency, fq=fq
        )

    try:
        init(host="127.0.0.1", port=7899, warm=False)
        print("🔗 已连接到 free-stockdb 本地服务: 127.0.0.1:7899")
    except Exception as e:
        print(f"❌ 连接 free-stockdb 服务失败: {e}")
        raise

    start_clean = start.replace('-', '')
    end_clean = end.replace('-', '')
    is_batch = len(stock_list) > 1

    try:
        result = rd.get_data(
            code=stock_list if is_batch else stock_list[0],
            start=start_clean,
            end=end_clean,
            frequency=frequency,
            fq=fq,
            fields="date,code,open,high,low,close,volume,name",
            as_df=True
        )

        if result is None or result.empty:
            print("❌ 未获取到任何数据")
            return metadata(price=pd.DataFrame(), benchmark=pd.Series())

        # 日期转换
        if 'date' in result.columns:
            result['date'] = pd.to_datetime(result['date'].astype(str), format='%Y%m%d', errors='coerce')
        else:
            print("⚠️ 返回数据中没有 'date' 列")
            return metadata(price=pd.DataFrame(), benchmark=pd.Series())

        result = result.dropna(subset=['date'])
        if result.empty:
            print("❌ 日期转换后数据为空")
            return metadata(price=pd.DataFrame(), benchmark=pd.Series())

        # ---------- 构建完整 OHLCV ----------
        if is_batch:
            info_df = result.drop_duplicates(subset=['code'])[['code', 'name']].set_index('code')
            price_df = result.pivot_table(index='date', columns='code', values='close')
            open_price_df = result.pivot_table(index='date', columns='code', values='open')
            high_price_df = result.pivot_table(index='date', columns='code', values='high')
            low_price_df = result.pivot_table(index='date', columns='code', values='low')
            volume_df = result.pivot_table(index='date', columns='code', values='volume')
            print(f"📊 批量加载: {len(price_df.columns)} 只股票，{len(price_df)} 个交易日")
        else:
            code = stock_list[0]
            name = result['name'].iloc[0] if 'name' in result.columns else code
            info_df = pd.DataFrame({'code': [code], 'name': [name]}).set_index('code')
            result = result.set_index('date')
            price_df = result[['close']].copy()
            price_df.columns = [code]
            open_price_df = result[['open']].copy()
            open_price_df.columns = [code]
            high_price_df = result[['high']].copy()
            high_price_df.columns = [code]
            low_price_df = result[['low']].copy()
            low_price_df.columns = [code]
            volume_df = result[['volume']].copy()
            volume_df.columns = [code]
            print(f"📊 单只股票 {code} 加载完成，{len(price_df)} 个交易日")

        if price_df.empty:
            print("❌ 价格数据为空")
            return metadata(price=pd.DataFrame(), benchmark=pd.Series())

        # 数据类型转换
        for col in price_df.columns:
            price_df[col] = pd.to_numeric(price_df[col], errors='coerce')

        # 构建基准（等权平均）
        benchmark = price_df.mean(axis=1)
        benchmark.name = 'EqualWeight'

        print(f"✅ 成功加载 {len(price_df.columns)} 只股票，{len(price_df)} 个交易日")
        print(f"📅 日期范围: {price_df.index.min()} 至 {price_df.index.max()}")

        return metadata(
            price=price_df,
            benchmark=benchmark,
            open_price=open_price_df,
            high_price=high_price_df,
            low_price=low_price_df,
            volume=volume_df,
            info=info_df
        ).align()

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
    elif source == 'stockdb_http':
        if 'tickers' in kwargs:
            kwargs['stock_list'] = kwargs.pop('tickers')
        return fetch_data_stockdb_http(**kwargs)
    else:
        raise ValueError("source 只支持 'yfinance', 'akshare', 'baostock', 'freestockdb' 或 'stockdb_http'")