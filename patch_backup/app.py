import sys
import os
sys.path.append(os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
import numpy as np
from core import load_data, AlphaScoreStrategy, BacktestPipeline
from utils.kline_plotter import plot_kline_with_trades
from core.data_structures import metadata
from config import *

# ---------- 导入 free-stockdb SDK ----------
try:
    from stock_sdk import rd, init, bk
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

st.set_page_config(page_title="量化回测系统", layout="wide")

# ---------- session_state 初始化 ----------
if 'initial_cash_memory' not in st.session_state:
    st.session_state.initial_cash_memory = 500000

st.title("📊 量化选股回测系统（Alpha剥离流水线）")

# ---------- 侧边栏：模式选择 ----------
mode = st.sidebar.radio(
    "选择功能",
    ["📈 回测", "📋 数据查看"],
    index=0
)

# ---------- 股票名称→代码映射（本地缓存） ----------
@st.cache_data(ttl=86400)
def get_name_to_code():
    """从本地数据构建名称→代码映射"""
    name_to_code = {}
    try:
        from stock_sdk import rd, init
        init(host="127.0.0.1", port=7899, warm=False)
        # 从日K键提取所有代码
        keys = rd.keys('日k', 'all:', 'all:')
        codes = set()
        for key in keys:
            parts = str(key).split(':')
            if len(parts) >= 3:
                code = parts[1]
                if code.isdigit() and len(code) == 6:
                    codes.add(code)
        # 尝试从bk获取名称
        try:
            from stock_sdk import bk
            boards = bk.get(category=1, fields="symbols,name")
            if boards and isinstance(boards, dict):
                for board_name, codes_in_board in boards.items():
                    if isinstance(codes_in_board, (list, tuple)):
                        for code in codes_in_board:
                            code_str = str(code).zfill(6)
                            if code_str in codes:
                                name_to_code[board_name] = code_str
        except:
            pass
        # 补充常用名称
        common_names = {
            "中兴通讯": "000063",
            "平安银行": "000001",
            "贵州茅台": "600519",
            "五粮液": "000858",
            "海康威视": "002415",
            "招商银行": "600036",
            "万科": "000002",
            "中国平安": "601318",
            "宁德时代": "300750",
            "比亚迪": "002594",
        }
        name_to_code.update(common_names)
        # 同时建立反向映射（代码→名称）
        code_to_name = {v: k for k, v in name_to_code.items()}
        return name_to_code, code_to_name
    except:
        return {}, {}

# ---------- 辅助函数 ----------
def calc_single_stock_performance(price_data):
    if price_data is None or price_data.empty:
        return None, None
    close = price_data['close']
    start = close.iloc[0]
    end = close.iloc[-1]
    ret = (end / start) - 1
    cummax = close.expanding().max()
    drawdown = (close - cummax) / cummax
    max_dd = drawdown.min()
    return ret, max_dd

def run_backtest():
    st.sidebar.header("⚙️ 回测参数")
    source = st.sidebar.selectbox(
        "数据源",
        ["freestockdb(本地引擎)", "本地CSV", "yfinance", "akshare", "baostock"],
        index=0
    )
    strategy_choice = st.sidebar.selectbox(
        "策略类型",
        ["Alpha剥离策略", "双均线金叉策略", "趋势跟踪策略"],
        index=1
    )

    test_mode = st.sidebar.radio(
        "测试模式",
        ["单次测试（不保存文件）", "继承性测试（保存文件+记住金额）"],
        index=0,
        help="单次测试：不保存任何图表和记录文件；继承性测试：正常保存所有文件，并记住上次输入的金额"
    )

    tickers_input = ""
    uploaded_file = None

    if source == "本地CSV":
        uploaded_file = st.sidebar.file_uploader(
            "📂 上传CSV文件",
            type=["csv"],
            help="支持标准OHLCV格式，列名需包含 date, open, high, low, close, volume"
        )
    elif source == "freestockdb(本地引擎)":
        tickers_input = st.sidebar.text_input(
            "股票代码 (逗号分隔)",
            value="000063"
        )
        st.sidebar.info(
            "🔗 需要先启动 free-stockdb 本地服务\n"
            "  下载: https://github.com/hello245m/free-stockdb\n"
            "  启动后端口: 127.0.0.1:7899"
        )
    else:
        tickers_input = st.sidebar.text_input(
            "股票代码 (逗号分隔)",
            value="AAPL,MSFT,GOOG,AMZN,TSLA" if source == "yfinance" else "000001,600519,000858,002415"
        )

    top_n = st.sidebar.number_input("持有股票数量 (Top N)", min_value=1, max_value=50, value=TOP_N)
    window = st.sidebar.number_input("滚动回归窗口 (天)", min_value=20, max_value=200, value=WINDOW)
    lookback = st.sidebar.number_input("残差动量回看 (天)", min_value=5, max_value=60, value=LOOKBACK)

    if test_mode == "继承性测试（保存文件+记住金额）":
        col_btn1, col_btn2, col_btn3, col_btn4 = st.sidebar.columns(4)
        if col_btn1.button("10万", key="btn_cash_1"):
            st.session_state.initial_cash_memory = 100000
        if col_btn2.button("50万", key="btn_cash_2"):
            st.session_state.initial_cash_memory = 500000
        if col_btn3.button("100万", key="btn_cash_3"):
            st.session_state.initial_cash_memory = 1000000
        if col_btn4.button("500万", key="btn_cash_4"):
            st.session_state.initial_cash_memory = 5000000

        initial_cash = st.sidebar.number_input(
            "初始资金 (元)",
            min_value=10000,
            max_value=100000000,
            value=st.session_state.initial_cash_memory,
            step=10000,
            key="cash_input"
        )
        st.session_state.initial_cash_memory = initial_cash
    else:
        initial_cash = st.sidebar.number_input(
            "初始资金 (元)",
            min_value=10000,
            max_value=100000000,
            value=500000,
            step=10000
        )

    default_end = pd.Timestamp.now() - pd.Timedelta(days=1)
    default_start = default_end - pd.DateOffset(years=1)

    start_date = st.sidebar.date_input(
        "开始日期",
        value=default_start,
        min_value=pd.to_datetime("2005-01-01"),
        max_value=default_end
    )
    end_date = st.sidebar.date_input(
        "结束日期",
        value=default_end,
        min_value=pd.to_datetime("2005-01-01"),
        max_value=default_end
    )

    # 模拟次日开盘价
    if test_mode == "单次测试（不保存文件）":
        st.sidebar.markdown("---")
        st.sidebar.subheader("🧪 模拟测试")
        sim_open_price = st.sidebar.number_input(
            "模拟次日开盘价",
            min_value=0.0,
            max_value=9999.99,
            value=0.0,
            step=0.01,
            help="输入一个模拟开盘价，查看该价格下的买卖信号"
        )
        if sim_open_price > 0:
            st.sidebar.info(f"📊 模拟开盘价: {sim_open_price:.2f}")
    else:
        sim_open_price = 0.0

    run_btn = st.sidebar.button("🚀 开始回测", type="primary")

    if run_btn:
        with st.spinner("正在加载数据并运行回测..."):
            try:
                # ---------- 数据加载 ----------
                if source == "本地CSV":
                    if uploaded_file is None:
                        st.error("请先上传CSV文件")
                        st.stop()
                    df = pd.read_csv(uploaded_file)
                    column_mapping = {
                        '日期': 'date', '交易日期': 'date', 'Date': 'date', 'date': 'date',
                        '开盘': 'open', '开盘价': 'open', 'Open': 'open', 'open': 'open',
                        '最高': 'high', '最高价': 'high', 'High': 'high', 'high': 'high',
                        '最低': 'low', '最低价': 'low', 'Low': 'low', 'low': 'low',
                        '收盘': 'close', '收盘价': 'close', 'Close': 'close', 'close': 'close',
                        'clsprc': 'close',
                        '成交量': 'volume', 'Volume': 'volume', 'volume': 'volume',
                        'stkcd': 'code', 'stock_code': 'code'
                    }
                    df.rename(columns=column_mapping, inplace=True)
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df.set_index('date')
                    else:
                        st.error("CSV文件中缺少 'date' 列")
                        st.stop()
                    if 'close' not in df.columns:
                        st.error("CSV文件中缺少 'close' 列")
                        st.stop()
                    if 'code' in df.columns:
                        price_df = df.pivot_table(index=df.index, columns='code', values='close')
                    else:
                        file_name = uploaded_file.name.replace('.csv', '')
                        price_df = df[['close']]
                        price_df.columns = [file_name]
                    benchmark = price_df.mean(axis=1)
                    benchmark.name = 'EqualWeight'
                    market_data = metadata(price=price_df, benchmark=benchmark).align()
                    st.sidebar.success(f"✅ 成功加载 {len(price_df.columns)} 只股票，{len(price_df)} 个交易日")
                elif source == "freestockdb(本地引擎)":
                    if not tickers_input.strip():
                        st.error("请输入股票代码")
                        st.stop()
                    tickers = [t.strip() for t in tickers_input.split(",") if t.strip()]
                    if not tickers:
                        st.error("请至少输入一个股票代码")
                        st.stop()
                    market_data = load_data(
                        source='freestockdb',
                        tickers=tickers,
                        start=start_date.strftime("%Y-%m-%d"),
                        end=end_date.strftime("%Y-%m-%d"),
                        frequency="1d",
                        fq="qfq"
                    )
                    st.sidebar.success(f"✅ 成功加载 {len(market_data.price.columns)} 只股票，{len(market_data.price)} 个交易日")
                else:
                    if not tickers_input.strip():
                        st.error("请输入股票代码")
                        st.stop()
                    tickers = [t.strip() for t in tickers_input.split(",") if t.strip()]
                    if not tickers:
                        st.error("请至少输入一个股票代码")
                        st.stop()
                    market_data = load_data(
                        source=source,
                        tickers=tickers,
                        start=start_date.strftime("%Y-%m-%d"),
                        end=end_date.strftime("%Y-%m-%d")
                    )

                if market_data.price.empty:
                    st.error("数据加载失败，请检查输入或网络")
                    st.stop()

                # ---------- 策略实例化 ----------
                if strategy_choice == "Alpha剥离策略":
                    from core.strategy import AlphaScoreStrategy
                    strategy = AlphaScoreStrategy(window=int(window), lookback=int(lookback))
                elif strategy_choice == "双均线金叉策略":
                    from core.strategy import SimpleStrategy
                    strategy = SimpleStrategy(short=5, long=20)
                else:
                    from core.strategy import TrendStrategy
                    strategy = TrendStrategy(period=20)

                engine = BacktestPipeline(strategy, top_n=int(top_n), commission=COMMISSION)

                auto_save = (test_mode == "继承性测试（保存文件+记住金额）")
                engine.run(market_data=market_data, initial_cash=initial_cash, auto_save=auto_save)

                # ---------- 绩效报告 ----------
                st.subheader("📈 组合绩效报告")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("累计收益率", f"{engine.total_return:.2%}")
                col2.metric("年化收益率", f"{engine.annual_return:.2%}")
                col3.metric("夏普比率", f"{engine.sharpe:.4f}")
                col4.metric("最大回撤", f"{engine.max_drawdown:.2%}")

                # ---------- 模拟信号显示 ----------
                if test_mode == "单次测试（不保存文件）" and sim_open_price > 0:
                    st.subheader("🧪 模拟次日开盘价信号")
                    try:
                        price_data = market_data.price
                        benchmark_price = market_data.benchmark_price if hasattr(market_data, 'benchmark_price') else None
                        if not price_data.empty and len(price_data) >= 2:
                            lookback = 60
                            hist_prices = price_data.iloc[-lookback:].copy()
                            if len(hist_prices) > 0:
                                hist_prices.iloc[-1, 0] = sim_open_price
                                sim_returns = hist_prices.pct_change().dropna()
                                if benchmark_price is not None and not benchmark_price.empty:
                                    common_idx = sim_returns.index.intersection(benchmark_price.index)
                                    if len(common_idx) > 0:
                                        sim_market_ret = benchmark_price.loc[common_idx].pct_change().dropna()
                                    else:
                                        sim_market_ret = sim_returns.mean(axis=1)
                                else:
                                    sim_market_ret = sim_returns.mean(axis=1)
                                score_series = engine.strategy.score_stocks(sim_returns, sim_market_ret)
                                if not score_series.empty:
                                    best_symbol = score_series.index[0]
                                    best_score = score_series.iloc[0]
                                    col_s1, col_s2, col_s3 = st.columns(3)
                                    col_s1.metric("📊 模拟开盘价", f"{sim_open_price:.2f}")
                                    col_s2.metric("📈 当前评分", f"{best_score:.3f}")
                                    if best_score > 0.1:
                                        col_s3.metric("💡 信号", "买入 ✅", delta="建议买入")
                                    elif best_score < -0.5:
                                        col_s3.metric("💡 信号", "卖出 ❌", delta="建议卖出")
                                    else:
                                        col_s3.metric("💡 信号", "持有 ⏸️", delta="无明确信号")
                                    st.caption(f"📌 基于模拟开盘价 {sim_open_price:.2f} 重新计算")
                                else:
                                    st.caption("⚠️ 策略未生成评分")
                            else:
                                st.caption("⚠️ 数据不足，无法模拟")
                        else:
                            st.caption("⚠️ 数据不足，无法模拟")
                    except Exception as e:
                        st.caption(f"⚠️ 模拟信号计算失败: {str(e)}")

                # ---------- 彩带 ----------
                if test_mode == "单次测试（不保存文件）":
                    st.subheader("📊 价格区间预兆（彩带）")
                    try:
                        price_data = market_data.price
                        benchmark_price = market_data.benchmark_price if hasattr(market_data, 'benchmark_price') else None
                        if not price_data.empty and len(price_data) >= 5:
                            lookback = min(60, len(price_data))
                            hist_prices = price_data.iloc[-lookback:].copy()
                            if len(hist_prices) > 5:
                                base_price = hist_prices.iloc[-2, 0] if len(hist_prices) > 1 else hist_prices.iloc[-1, 0]
                                price_range = np.linspace(base_price * 0.80, base_price * 1.20, 50)
                                scores_list = []
                                buy_prices = []
                                sell_prices = []
                                hold_prices = []
                                for test_price in price_range:
                                    test_prices = hist_prices.copy()
                                    test_prices.iloc[-1, 0] = test_price
                                    test_returns = test_prices.pct_change().dropna()
                                    if benchmark_price is not None and not benchmark_price.empty:
                                        common_idx = test_returns.index.intersection(benchmark_price.index)
                                        if len(common_idx) > 0:
                                            test_market_ret = benchmark_price.loc[common_idx].pct_change().dropna()
                                        else:
                                            test_market_ret = test_returns.mean(axis=1)
                                    else:
                                        test_market_ret = test_returns.mean(axis=1)
                                    test_scores = engine.strategy.score_stocks(test_returns, test_market_ret)
                                    if not test_scores.empty:
                                        test_score = test_scores.iloc[0]
                                        scores_list.append((test_price, test_score))
                                        if test_score > 0.1:
                                            buy_prices.append(test_price)
                                        elif test_score < -0.5:
                                            sell_prices.append(test_price)
                                        else:
                                            hold_prices.append(test_price)
                                st.caption(f"📊 调试信息：数据长度 = {len(price_data)}，回看天数 = {lookback}，测试价格点数 = {len(price_range)}")
                                st.caption(f"📊 评分结果数 = {len(scores_list)}，买入触发价数 = {len(buy_prices)}，卖出触发价数 = {len(sell_prices)}，持有价数 = {len(hold_prices)}")
                                if scores_list:
                                    scores = [s[1] for s in scores_list]
                                    st.caption(f"📊 评分范围：{min(scores):.3f} ~ {max(scores):.3f}")
                                if len(buy_prices) == 0 and len(sell_prices) == 0:
                                    st.warning("⚠️ 当前策略在所有测试价格下均无买入/卖出信号，可能数据不足或策略条件未触发。")
                                if scores_list:
                                    prices = [s[0] for s in scores_list]
                                    scores = [s[1] for s in scores_list]
                                    norm_scores = np.clip(np.array(scores) / 1.0, -1, 1)
                                    fig, ax = plt.subplots(figsize=(10, 1.2))
                                    colors = []
                                    for s in norm_scores:
                                        if s > 0.3:
                                            g = min(1.0, s)
                                            colors.append((0.2, 0.7 + 0.3*g, 0.2))
                                        elif s < -0.3:
                                            r = min(1.0, abs(s))
                                            colors.append((0.7 + 0.3*r, 0.2, 0.2))
                                        else:
                                            t = (s + 0.3) / 0.6
                                            gray = 0.5 + 0.3 * t
                                            colors.append((gray, gray, gray))
                                    for i in range(len(prices) - 1):
                                        ax.barh(0, prices[i+1]-prices[i], left=prices[i], height=0.6,
                                                color=colors[i], edgecolor='none')
                                    if buy_prices:
                                        ax.axvline(x=buy_prices[0], color='green', linestyle='-', linewidth=2, alpha=0.7)
                                        ax.axvline(x=buy_prices[-1], color='green', linestyle='-', linewidth=2, alpha=0.7)
                                        ax.text(buy_prices[0], 0.7, f'买入区', color='green', ha='center', fontsize=10, weight='bold')
                                    if sell_prices:
                                        ax.axvline(x=sell_prices[0], color='red', linestyle='-', linewidth=2, alpha=0.7)
                                        ax.axvline(x=sell_prices[-1], color='red', linestyle='-', linewidth=2, alpha=0.7)
                                        ax.text(sell_prices[0], 0.7, f'卖出区', color='red', ha='center', fontsize=10, weight='bold')
                                    if hold_prices:
                                        ax.text((hold_prices[0]+hold_prices[-1])/2, -0.5,
                                                f'持有区 {hold_prices[0]:.2f}~{hold_prices[-1]:.2f}',
                                                color='gray', ha='center', fontsize=9)
                                    if sim_open_price > 0 and prices[0] <= sim_open_price <= prices[-1]:
                                        ax.axvline(x=sim_open_price, color='blue', linestyle='--', linewidth=2, alpha=0.9)
                                        ax.text(sim_open_price, -0.5, f'← 当前价 {sim_open_price:.2f}', color='blue', ha='center', fontsize=9, weight='bold')
                                    ax.set_xlim(prices[0], prices[-1])
                                    ax.set_ylim(-0.8, 0.8)
                                    ax.set_yticks([])
                                    ax.spines['top'].set_visible(False)
                                    ax.spines['bottom'].set_visible(False)
                                    ax.spines['left'].set_visible(False)
                                    ax.spines['right'].set_visible(False)
                                    ax.tick_params(axis='x', labelsize=9)
                                    ax.set_xlabel('价格', fontsize=9)
                                    plt.tight_layout()
                                    st.pyplot(fig)
                                    plt.close()
                                    st.caption("💡 绿色=买入区 | 灰色=持有区 | 红色=卖出区 | 蓝色虚线=模拟开盘价")
                                else:
                                    st.caption("⚠️ 未生成任何评分，无法绘制彩带")
                            else:
                                st.caption("⚠️ 历史数据不足，无法生成彩带")
                        else:
                            st.caption("⚠️ 数据不足，无法生成彩带")
                    except Exception as e:
                        st.caption(f"⚠️ 彩带绘制失败: {str(e)}")

                # ---------- 净值曲线 ----------
                st.subheader("📉 资金曲线与回撤分析")
                fig = engine.plot_performance(return_fig=True)
                if fig is None or not isinstance(fig, go.Figure):
                    st.error("图表生成失败，请检查数据量。")
                else:
                    st.plotly_chart(fig, width='stretch')

                # ---------- 个股K线图 ----------
                with st.expander("📊 查看个股K线图与买卖点"):
                    stock_list = market_data.price.columns.tolist()
                    if source == "freestockdb(本地引擎)":
                        ohlc_cache = {}
                        for code in stock_list:
                            try:
                                from stock_sdk import rd, init
                                init(host="127.0.0.1", port=7899, warm=False)
                                ohlc = rd.get_data(
                                    code=code,
                                    start=start_date.strftime("%Y%m%d"),
                                    end=end_date.strftime("%Y%m%d"),
                                    frequency="1d",
                                    fq="qfq",
                                    fields="date,open,high,low,close,volume",
                                    as_df=True
                                )
                                if ohlc is not None and not ohlc.empty:
                                    ohlc['date'] = pd.to_datetime(ohlc['date'].astype(str), format='%Y%m%d')
                                    ohlc = ohlc.set_index('date')
                                    if all(c in ohlc.columns for c in ['open','high','low','close']):
                                        ohlc_cache[code] = ohlc
                                    else:
                                        ohlc_cache[code] = None
                                else:
                                    ohlc_cache[code] = None
                            except Exception as e:
                                ohlc_cache[code] = None
                    else:
                        ohlc_cache = None

                    if ohlc_cache is None or all(v is None for v in ohlc_cache.values()):
                        st.warning("无法获取OHLC数据，请使用 free-stockdb 数据源以查看K线图。")
                    else:
                        trades_df = engine.get_trades_df()
                        compare_mode = st.checkbox("🔄 对比模式（并排显示所有股票的K线图）", value=False)
                        if compare_mode:
                            cols_per_row = 2
                            valid_stocks = [code for code in stock_list if code in ohlc_cache and ohlc_cache[code] is not None]
                            if not valid_stocks:
                                st.warning("没有可用的股票数据。")
                            else:
                                for i in range(0, len(valid_stocks), cols_per_row):
                                    row_stocks = valid_stocks[i:i+cols_per_row]
                                    cols = st.columns(cols_per_row)
                                    for j, code in enumerate(row_stocks):
                                        with cols[j]:
                                            ohlc = ohlc_cache[code]
                                            stock_name = market_data.info.loc[code, 'name'] if code in market_data.info.index else code
                                            ret, max_dd = calc_single_stock_performance(ohlc[['close']])
                                            st.metric(f"{code} {stock_name}", f"涨跌: {ret:.2%}", f"回撤: {max_dd:.2%}")
                                            if trades_df is not None and not trades_df.empty:
                                                stock_trades = trades_df[trades_df['Stock'] == code]
                                            else:
                                                stock_trades = pd.DataFrame()
                                            fig = plot_kline_with_trades(ohlc, stock_trades, code, stock_name)
                                            st.plotly_chart(fig, width='stretch')
                        else:
                            for code in stock_list:
                                if code not in ohlc_cache or ohlc_cache[code] is None:
                                    st.warning(f"⚠️ 无法获取 {code} 的OHLC数据，跳过。")
                                    continue
                                ohlc = ohlc_cache[code]
                                stock_name = market_data.info.loc[code, 'name'] if code in market_data.info.index else code
                                ret, max_dd = calc_single_stock_performance(ohlc[['close']])
                                col_ret, col_dd = st.columns(2)
                                col_ret.metric(f"{code} {stock_name} 期间涨跌幅", f"{ret:.2%}" if ret is not None else "N/A")
                                col_dd.metric(f"{code} {stock_name} 最大回撤", f"{max_dd:.2%}" if max_dd is not None else "N/A")
                                if trades_df is not None and not trades_df.empty:
                                    stock_trades = trades_df[trades_df['Stock'] == code]
                                else:
                                    stock_trades = pd.DataFrame()
                                fig = plot_kline_with_trades(ohlc, stock_trades, code, stock_name)
                                st.plotly_chart(fig, width='stretch')
                                st.divider()

                # ---------- 交易记录 ----------
                with st.expander("📋 查看最近交易记录"):
                    trades_df = engine.get_trades_df()
                    if trades_df is not None and not trades_df.empty:
                        trades_display = trades_df.tail(20).copy()
                        trades_display.rename(columns={
                            'Date': '日期',
                            'Stock': '股票',
                            'Action': '操作',
                            'Price': '价格',
                            'Shares': '数量'
                        }, inplace=True)
                        trades_display['操作'] = trades_display['操作'].replace({'BUY': '买入', 'SELL': '卖出'})
                        st.dataframe(trades_display)
                    else:
                        st.write("暂无交易记录")

                # ---------- 评分明细 ----------
                with st.expander("📊 查看每日评分明细（最近20个交易日）"):
                    if hasattr(engine, 'daily_scores') and engine.daily_scores:
                        score_records = []
                        for date, scores in engine.daily_scores.items():
                            if scores:
                                for stock, score in scores.items():
                                    score_records.append({
                                        '日期': date.strftime('%Y-%m-%d'),
                                        '股票': stock,
                                        'Alpha得分': round(score, 4)
                                    })
                        if score_records:
                            score_df = pd.DataFrame(score_records)
                            recent_dates = score_df['日期'].unique()[-20:]
                            score_df_recent = score_df[score_df['日期'].isin(recent_dates)]
                            st.dataframe(score_df_recent, width='stretch')

                            st.caption(f"📌 每个交易日选中的前 {int(top_n)} 只股票")
                            selected_records = []
                            for date, selected in engine.daily_selected.items():
                                if selected:
                                    selected_records.append({
                                        '日期': date.strftime('%Y-%m-%d'),
                                        '选中股票': ', '.join(selected[:int(top_n)])
                                    })
                            if selected_records:
                                selected_df = pd.DataFrame(selected_records)
                                selected_df_recent = selected_df[selected_df['日期'].isin(recent_dates)]
                                st.dataframe(selected_df_recent, width='stretch')
                        else:
                            st.write("暂无评分数据")
                    else:
                        st.write("回测引擎未记录评分明细")

            except Exception as e:
                st.error(f"运行出错: {str(e)}")
                import traceback
                st.code(traceback.format_exc())

# ---------- 模式2：数据查看（直接输入股票代码） ----------
def run_data_viewer():
    st.sidebar.header("📋 数据查看参数")
    st.sidebar.info("💡 直接输入股票代码或名称，按回车加载数据")

    # 获取名称映射
    name_to_code, code_to_name = get_name_to_code()

    # 输入框
    code_input = st.sidebar.text_input(
        "股票代码或名称",
        value="000063",
        placeholder="例如 000063 或 中兴通讯"
    )

    if not code_input:
        st.sidebar.warning("请输入股票代码或名称")
        return

    # 解析输入
    code_str = code_input.strip()
    selected_code = code_str

    # 如果是6位数字，直接使用
    if code_str.isdigit() and len(code_str) == 6:
        selected_code = code_str
    else:
        # 尝试从映射查找
        if code_str in name_to_code:
            selected_code = name_to_code[code_str]
            st.sidebar.success(f"✅ 找到股票: {code_str} -> {selected_code}")
        else:
            # 尝试作为代码
            st.sidebar.warning(f"未找到名称映射，将尝试作为代码使用: {selected_code}")

    # 如果不是6位数字，报错
    if not (selected_code.isdigit() and len(selected_code) == 6):
        st.sidebar.error(f"无效的股票代码: {selected_code}")
        return

    # 获取名称（用于显示）
    selected_name = code_to_name.get(selected_code, selected_code)

    default_end = pd.Timestamp.now() - pd.Timedelta(days=1)
    default_start = default_end - pd.DateOffset(years=1)

    start_date = st.sidebar.date_input("开始日期", value=default_start, min_value=pd.to_datetime("2005-01-01"))
    end_date = st.sidebar.date_input("结束日期", value=default_end, min_value=pd.to_datetime("2005-01-01"))
    frequency = st.sidebar.selectbox("周期频率", ["1d","1m","5m","15m","30m","60m","1w","1M"], index=0)
    fq_type = st.sidebar.selectbox("复权类型", ["qfq","hfq","none"], index=0)
    show_table = st.sidebar.checkbox("显示数据表格", value=False)

    load_btn = st.sidebar.button("📊 加载数据", type="primary")

    if load_btn:
        if not SDK_AVAILABLE:
            st.error("free-stockdb SDK 未正确配置。")
            return
        with st.spinner(f"加载 {selected_code}..."):
            try:
                init(host="127.0.0.1", port=7899, warm=False)
                start_str = start_date.strftime("%Y%m%d")
                end_str = end_date.strftime("%Y%m%d")
                data = rd.get_data(
                    code=selected_code,
                    start=start_str,
                    end=end_str,
                    frequency=frequency,
                    fq=fq_type,
                    fields="date,open,high,low,close,volume,amount,name",
                    as_df=True
                )
                if data is None or data.empty:
                    st.warning("未获取到数据")
                    return
                if 'date' in data.columns:
                    data['date'] = pd.to_datetime(data['date'].astype(str), format='%Y%m%d', errors='coerce')
                    data = data.dropna(subset=['date'])
                    data = data.set_index('date')
                # 显示名称（如果有）
                if 'name' in data.columns:
                    actual_name = data['name'].iloc[0]
                    st.caption(f"📌 股票名称: {actual_name} ({selected_code})")

                if frequency in ['1d','1w','1M'] and all(c in data.columns for c in ['open','high','low','close']):
                    date_str = data.index.strftime('%Y-%m-%d')
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(
                        x=date_str,
                        open=data['open'],
                        high=data['high'],
                        low=data['low'],
                        close=data['close'],
                        name='K线',
                        increasing_line_color='red',
                        decreasing_line_color='green'
                    ))
                    if 'close' in data.columns:
                        ma5 = data['close'].rolling(5).mean()
                        ma20 = data['close'].rolling(20).mean()
                        fig.add_trace(go.Scatter(x=date_str, y=ma5, mode='lines', name='MA5', line=dict(color='orange', width=1.5)))
                        fig.add_trace(go.Scatter(x=date_str, y=ma20, mode='lines', name='MA20', line=dict(color='purple', width=1.5)))
                    fig.update_layout(
                        title=f"{selected_code} {selected_name} {frequency} K线图 (MA5, MA20)",
                        xaxis_title="日期",
                        yaxis_title="价格",
                        template='plotly_white',
                        height=600,
                        hovermode='x unified',
                        xaxis=dict(type='category', tickangle=45)
                    )
                    st.plotly_chart(fig, width='stretch')
                else:
                    if 'close' in data.columns:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=data.index,
                            y=data['close'],
                            mode='lines',
                            name='收盘价',
                            connectgaps=False
                        ))
                        fig.update_layout(
                            title=f"{selected_code} {selected_name} {frequency} 收盘价走势",
                            xaxis_title="时间",
                            yaxis_title="价格",
                            template='plotly_white',
                            height=500
                        )
                        st.plotly_chart(fig, width='stretch')
                    else:
                        st.warning("无收盘价列")
                if show_table:
                    st.dataframe(data)
                csv = data.to_csv(index=True).encode('utf-8')
                st.download_button(label="📥 下载CSV", data=csv, file_name=f"{selected_code}_{frequency}_{start_str}_{end_str}.csv", mime="text/csv")
            except Exception as e:
                st.error(f"加载失败: {e}")

# ---------- 主入口 ----------
if mode == "📈 回测":
    run_backtest()
else:
    run_data_viewer()