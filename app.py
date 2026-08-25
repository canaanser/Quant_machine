import sys
import os
sys.path.append(os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False
import numpy as np
from core import load_data, AlphaScoreStrategy, BacktestPipeline
from utils.kline_plotter import plot_kline_with_trades
from core.data_structures import metadata
from config import *

DEBUG_MODE = True

try:
    from stock_sdk import rd, init, bk
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

st.set_page_config(page_title="量化回测系统", layout="wide")

if 'initial_cash_memory' not in st.session_state:
    st.session_state.initial_cash_memory = 500000

st.title("📊 量化选股回测系统（Alpha剥离流水线）")

mode = st.sidebar.radio(
    "选择功能",
    ["📈 回测", "📋 数据查看", "🔍 形态诊断"],
    index=0
)

# ---------- 股票名称→代码映射 ----------
@st.cache_data(ttl=86400)
def get_name_to_code():
    name_to_code = {}
    try:
        from stock_sdk import rd, init
        init(host="127.0.0.1", port=7899, warm=False)
        keys = rd.keys('日k', 'all:', 'all:')
        codes = set()
        for key in keys:
            parts = str(key).split(':')
            if len(parts) >= 3:
                code = parts[1]
                if code.isdigit() and len(code) == 6:
                    codes.add(code)
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
        code_to_name = {v: k for k, v in name_to_code.items()}
        return name_to_code, code_to_name
    except:
        return {}, {}

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

def get_stock_type(code: str, tags=None) -> dict:
    code = str(code).strip()
    if tags:
        tags_str = str(tags).upper()
        if 'ST' in tags_str:
            return {'limit': 0.05, 'type': 'ST/*ST', 'label': '±5%'}
    if code.startswith('300'):
        return {'limit': 0.20, 'type': '创业板', 'label': '±20%'}
    elif code.startswith('688'):
        return {'limit': 0.20, 'type': '科创板', 'label': '±20%'}
    elif code.startswith('8'):
        return {'limit': 0.30, 'type': '北交所', 'label': '±30%'}
    elif code.startswith('60') or code.startswith('00'):
        return {'limit': 0.10, 'type': '主板', 'label': '±10%'}
    else:
        return {'limit': 0.10, 'type': '默认', 'label': '±10%'}

def calc_simulated_score(sim_close, open_price, close_prev, ma5_prev, ma20_prev, close_5_ago, close_20_ago):
    sim_ma5 = (ma5_prev * 5 - close_5_ago + sim_close) / 5
    sim_ma20 = (ma20_prev * 20 - close_20_ago + sim_close) / 20
    sim_diff = sim_ma5 - sim_ma20
    prev_diff = ma5_prev - ma20_prev
    accel = sim_diff - prev_diff
    score = 0.5 + accel * 2.0
    return np.clip(score, 0.0, 1.0)


# ==================== 回测功能 ====================
def run_backtest():
    st.sidebar.header("⚙️ 回测参数")
    source = st.sidebar.selectbox(
        "数据源",
        ["freestockdb(本地引擎)", "本地CSV", "yfinance", "akshare", "baostock"],
        index=0
    )
    strategy_choice = st.sidebar.selectbox(
        "策略类型",
        ["Alpha剥离策略", "双均线金叉策略", "趋势跟踪策略", "趋势强度策略"],
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

    if test_mode == "单次测试（不保存文件）":
        st.sidebar.markdown("---")
        st.sidebar.subheader("🧪 早盘信号图谱")
        sim_open_price = st.sidebar.number_input(
            "模拟开盘价",
            min_value=0.0,
            max_value=9999.99,
            value=0.0,
            step=0.01,
            help="输入一个模拟开盘价，系统自动识别股票类型并计算涨跌停区间"
        )
        if sim_open_price > 0:
            st.sidebar.info(f"📊 模拟开盘价: {sim_open_price:.2f}")
    else:
        sim_open_price = 0.0

    run_btn = st.sidebar.button("🚀 开始回测", type="primary")

    if run_btn:
        with st.spinner("正在加载数据并运行回测..."):
            try:
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

                if strategy_choice == "Alpha剥离策略":
                    from core.strategy import AlphaScoreStrategy
                    strategy = AlphaScoreStrategy(window=int(window), lookback=int(lookback))
                elif strategy_choice == "双均线金叉策略":
                    from core.strategy import SimpleStrategy
                    strategy = SimpleStrategy(short=5, long=20)
                elif strategy_choice == "趋势跟踪策略":
                    from core.strategy import TrendStrategy
                    strategy = TrendStrategy(period=20)
                elif strategy_choice == "趋势强度策略":
                    from core.strategy import TrendStrengthStrategy
                    strategy = TrendStrengthStrategy(short=5, long=20)

                engine = BacktestPipeline(strategy, top_n=int(top_n), verbose=DEBUG_MODE, commission=COMMISSION)

                auto_save = (test_mode == "继承性测试（保存文件+记住金额）")
                engine.run(market_data=market_data, initial_cash=initial_cash, auto_save=auto_save)

                st.subheader("📈 组合绩效报告")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("累计收益率", f"{engine.total_return:.2%}")
                col2.metric("年化收益率", f"{engine.annual_return:.2%}")
                col3.metric("夏普比率", f"{engine.sharpe:.4f}")
                col4.metric("最大回撤", f"{engine.max_drawdown:.2%}")

                if test_mode == "单次测试（不保存文件）" and sim_open_price > 0:
                    st.subheader("🧪 模拟次日开盘价信号")
                    try:
                        price_data = market_data.price
                        if not price_data.empty and len(price_data) >= 2:
                            lookback = min(60, len(price_data))
                            hist_prices = price_data.iloc[-lookback:].copy()
                            if len(hist_prices) > 1:
                                early_score = 0.5
                                try:
                                    last_close = hist_prices.iloc[-2, 0]
                                    if len(hist_prices) >= 6:
                                        last_ma5 = hist_prices['close'].rolling(5).mean().iloc[-2] if 'close' in hist_prices.columns else hist_prices.iloc[-2, 0]
                                    else:
                                        last_ma5 = last_close
                                    if len(hist_prices) >= 21:
                                        last_ma20 = hist_prices['close'].rolling(20).mean().iloc[-2] if 'close' in hist_prices.columns else hist_prices.iloc[-2, 0]
                                    else:
                                        last_ma20 = last_close
                                    if hasattr(engine.strategy, 'calculate_early_score'):
                                        early_score = engine.strategy.calculate_early_score(
                                            open_price=sim_open_price,
                                            close_prev=last_close,
                                            ma5_prev=last_ma5,
                                            ma20_prev=last_ma20
                                        )
                                except Exception as e:
                                    early_score = 0.5
                                
                                col_s1, col_s2, col_s3 = st.columns(3)
                                col_s1.metric("📊 模拟开盘价", f"{sim_open_price:.2f}")
                                col_s2.metric("📈 早盘评分", f"{early_score:.3f}")
                                if early_score > 0.6:
                                    col_s3.metric("💡 信号", "偏多 ✅", delta="建议关注")
                                elif early_score < 0.4:
                                    col_s3.metric("💡 信号", "偏空 ❌", delta="建议谨慎")
                                else:
                                    col_s3.metric("💡 信号", "中性 ⏸️", delta="无明确方向")
                                st.caption(f"📌 基于模拟开盘价 {sim_open_price:.2f} 计算早盘偏离度（阈值1.5%）")
                            else:
                                st.caption("⚠️ 数据不足，无法模拟")
                        else:
                            st.caption("⚠️ 数据不足，无法模拟")
                    except Exception as e:
                        st.caption(f"⚠️ 模拟信号计算失败: {str(e)}")

                if test_mode == "单次测试（不保存文件）":
                    st.subheader("📊 价格区间预兆（彩带）")
                    try:
                        price_data = market_data.price
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
                                
                                last_close = hist_prices.iloc[-2, 0] if len(hist_prices) > 1 else hist_prices.iloc[-1, 0]
                                if len(hist_prices) >= 6:
                                    last_ma5 = hist_prices['close'].rolling(5).mean().iloc[-2] if 'close' in hist_prices.columns else last_close
                                else:
                                    last_ma5 = last_close
                                if len(hist_prices) >= 21:
                                    last_ma20 = hist_prices['close'].rolling(20).mean().iloc[-2] if 'close' in hist_prices.columns else last_close
                                else:
                                    last_ma20 = last_close
                                
                                for test_price in price_range:
                                    try:
                                        if hasattr(engine.strategy, 'calculate_early_score'):
                                            test_score = engine.strategy.calculate_early_score(
                                                open_price=test_price,
                                                close_prev=last_close,
                                                ma5_prev=last_ma5,
                                                ma20_prev=last_ma20
                                            )
                                        else:
                                            test_score = 0.5
                                    except Exception:
                                        test_score = 0.5
                                    
                                    scores_list.append((test_price, test_score))
                                    if test_score > 0.6:
                                        buy_prices.append(test_price)
                                    elif test_score < 0.4:
                                        sell_prices.append(test_price)
                                    else:
                                        hold_prices.append(test_price)
                                
                                st.caption(f"📊 调试信息：数据长度 = {len(price_data)}，回看天数 = {lookback}，测试价格点数 = {len(price_range)}")
                                st.caption(f"📊 评分结果数 = {len(scores_list)}，偏多价数 = {len(buy_prices)}，偏空价数 = {len(sell_prices)}，中性价数 = {len(hold_prices)}")
                                if scores_list:
                                    scores = [s[1] for s in scores_list]
                                    st.caption(f"📊 早盘评分范围：{min(scores):.3f} ~ {max(scores):.3f}")
                                if len(buy_prices) == 0 and len(sell_prices) == 0:
                                    st.warning("⚠️ 当前价格区间下早盘评分全部为中性，可能阈值设得偏保守。")
                                if scores_list:
                                    prices = [s[0] for s in scores_list]
                                    scores = [s[1] for s in scores_list]
                                    fig, ax = plt.subplots(figsize=(10, 1.2))
                                    colors = []
                                    for s in scores:
                                        if s > 0.6:
                                            colors.append((0.1, 0.8, 0.1))
                                        elif s < 0.4:
                                            colors.append((0.8, 0.1, 0.1))
                                        else:
                                            colors.append((0.6, 0.6, 0.6))
                                    for i in range(len(prices) - 1):
                                        ax.barh(0, prices[i+1]-prices[i], left=prices[i], height=0.6,
                                                color=colors[i], edgecolor='none')
                                    if buy_prices:
                                        ax.axvline(x=buy_prices[0], color='green', linestyle='-', linewidth=2, alpha=0.7)
                                        ax.axvline(x=buy_prices[-1], color='green', linestyle='-', linewidth=2, alpha=0.7)
                                        ax.text(buy_prices[0], 0.7, f'偏多区', color='green', ha='center', fontsize=10, weight='bold')
                                    if sell_prices:
                                        ax.axvline(x=sell_prices[0], color='red', linestyle='-', linewidth=2, alpha=0.7)
                                        ax.axvline(x=sell_prices[-1], color='red', linestyle='-', linewidth=2, alpha=0.7)
                                        ax.text(sell_prices[0], 0.7, f'偏空区', color='red', ha='center', fontsize=10, weight='bold')
                                    if hold_prices:
                                        ax.text((hold_prices[0]+hold_prices[-1])/2, -0.5,
                                                f'中性区 {hold_prices[0]:.2f}~{hold_prices[-1]:.2f}',
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
                                    st.caption("💡 绿色=偏多区 | 灰色=中性区 | 红色=偏空区 | 蓝色虚线=模拟开盘价")
                                else:
                                    st.caption("⚠️ 未生成任何评分，无法绘制彩带")
                            else:
                                st.caption("⚠️ 历史数据不足，无法生成彩带")
                        else:
                            st.caption("⚠️ 数据不足，无法生成彩带")
                    except Exception as e:
                        st.caption(f"⚠️ 彩带绘制失败: {str(e)}")

                st.subheader("📉 资金曲线与回撤分析")
                fig = engine.plot_performance(return_fig=True)
                if fig is None or not isinstance(fig, go.Figure):
                    st.error("图表生成失败，请检查数据量。")
                else:
                    st.plotly_chart(fig, width='stretch')

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
                                            ohlc = ohlc_cache[code].copy()
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
                                ohlc = ohlc_cache[code].copy()
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

                with st.expander("📊 早盘评分明细（最近20个交易日）"):
                    if hasattr(engine, 'daily_early_scores') and engine.daily_early_scores:
                        early_records = []
                        for date, score in engine.daily_early_scores.items():
                            early_records.append({
                                '日期': date.strftime('%Y-%m-%d'),
                                '早盘评分': round(score, 4)
                            })
                        if early_records:
                            early_df = pd.DataFrame(early_records)
                            early_df = early_df.sort_values('日期', ascending=False).head(20)
                            st.dataframe(early_df, width='stretch')
                            st.caption("📌 早盘评分 = 开盘价相对昨日MA20的偏离度映射值（0~1），纯展示，不参与交易决策")
                    else:
                        st.write("暂无早盘评分数据")

            except Exception as e:
                st.error(f"运行出错: {str(e)}")
                import traceback
                st.code(traceback.format_exc())


# ==================== 数据查看功能 ====================
def run_data_viewer():
    st.sidebar.header("📋 数据查看参数")
    st.sidebar.info("💡 直接输入股票代码或名称，按回车加载数据")

    name_to_code, code_to_name = get_name_to_code()

    code_input = st.sidebar.text_input(
        "股票代码或名称",
        value="000063",
        placeholder="例如 000063 或 中兴通讯"
    )

    if not code_input:
        st.sidebar.warning("请输入股票代码或名称")
        return

    code_str = code_input.strip()
    selected_code = code_str

    if code_str.isdigit() and len(code_str) == 6:
        selected_code = code_str
    else:
        if code_str in name_to_code:
            selected_code = name_to_code[code_str]
            st.sidebar.success(f"✅ 找到股票: {code_str} -> {selected_code}")
        else:
            st.sidebar.warning(f"未找到名称映射，将尝试作为代码使用: {selected_code}")

    if not (selected_code.isdigit() and len(selected_code) == 6):
        st.sidebar.error(f"无效的股票代码: {selected_code}")
        return

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


# ==================== 形态诊断功能 ====================
def run_pattern_diagnosis():
    st.sidebar.header("🔍 形态诊断参数")
    st.sidebar.info("输入股票代码，系统将展示近期形态匹配、位置标签和电子云统计")

    name_to_code, code_to_name = get_name_to_code()

    code_input = st.sidebar.text_input(
        "股票代码或名称",
        value="600498",
        placeholder="例如 000063 或 中兴通讯"
    )

    if not code_input:
        st.sidebar.warning("请输入股票代码或名称")
        return

    code_str = code_input.strip()
    selected_code = code_str
    if code_str.isdigit() and len(code_str) == 6:
        selected_code = code_str
    else:
        if code_str in name_to_code:
            selected_code = name_to_code[code_str]
            st.sidebar.success(f"✅ 找到股票: {code_str} -> {selected_code}")
        else:
            st.sidebar.warning(f"未找到名称映射，将尝试作为代码使用: {selected_code}")

    if not (selected_code.isdigit() and len(selected_code) == 6):
        st.sidebar.error(f"无效的股票代码: {selected_code}")
        return

    selected_name = code_to_name.get(selected_code, selected_code)

    # ===== 诊断窗口默认改为最近30天 =====
    default_end = pd.Timestamp.now() - pd.Timedelta(days=1)
    default_start = default_end - pd.DateOffset(days=30)  # 30天
    start_date = st.sidebar.date_input("开始日期（诊断窗口）", value=default_start, min_value=pd.to_datetime("2005-01-01"))
    end_date = st.sidebar.date_input("结束日期", value=default_end, min_value=pd.to_datetime("2005-01-01"))

    # ===== 是否显示形态名称标签 =====
    show_labels = st.sidebar.checkbox("显示形态名称标签", value=False)

    diagnose_btn = st.sidebar.button("🔍 诊断", type="primary")

    if diagnose_btn:
        with st.spinner(f"正在诊断 {selected_code}..."):
            try:
                import sqlite3
                from pathlib import Path
                from core.data_loader import load_data
                from utils.kline_plotter import plot_kline_with_trades

                DB_PATH = Path("data/index_store/pattern_history.db")
                if not DB_PATH.exists():
                    st.error("数据库文件不存在，请先运行扫描")
                    return

                conn = sqlite3.connect(str(DB_PATH))
                cursor = conn.cursor()

                start_str = start_date.strftime('%Y-%m-%d')
                end_str = end_date.strftime('%Y-%m-%d')

                # 查询 ready 记录（不含 strength 列）
                cursor.execute("""
                    SELECT pattern_id, pattern_name, band_position, match_date, match_price,
                           peak_date, valley_date, composite_return, base_score
                    FROM pattern_history
                    WHERE symbol = ?
                      AND match_date >= ? AND match_date <= ?
                      AND band_position_ready = 1
                      AND composite_return IS NOT NULL
                    ORDER BY match_date DESC
                """, (selected_code, start_str, end_str))

                rows = cursor.fetchall()

                if not rows:
                    st.warning(f"⚠️ 在 {start_str} 至 {end_str} 期间，未找到 {selected_code} 的 ready 形态记录")
                    st.caption("💡 提示：请确保该股票已扫描，且形态位置已确认（band_position_ready=1）")
                    conn.close()
                    return

                st.subheader(f"📊 {selected_code} {selected_name} 形态诊断结果")
                st.caption(f"📅 诊断窗口: {start_str} 至 {end_str} | 共 {len(rows)} 条匹配记录")

                data = []
                for row in rows:
                    pattern_id, pattern_name, band_pos, match_date, match_price, peak_date, valley_date, comp_ret, base_score = row

                    cursor.execute("""
                        SELECT COUNT(*) as cnt,
                               AVG(composite_return) as avg_ret,
                               SUM(CASE WHEN composite_return > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate
                        FROM pattern_history
                        WHERE symbol = ?
                          AND pattern_id = ?
                          AND band_position = ?
                          AND band_position_ready = 1
                          AND composite_return IS NOT NULL
                    """, (selected_code, pattern_id, band_pos))

                    stat_row = cursor.fetchone()
                    sample_cnt = stat_row[0] if stat_row[0] else 0
                    avg_ret = stat_row[1] if stat_row[1] is not None else 0.0
                    win_rate = stat_row[2] if stat_row[2] is not None else 0.0

                    data.append({
                        "形态": pattern_name,
                        "位置": band_pos,
                        "匹配日期": match_date,
                        "收盘价": match_price,
                        "历史样本": sample_cnt,
                        "历史平均收益": f"{avg_ret:.2%}" if avg_ret else "N/A",
                        "历史胜率": f"{win_rate:.0%}" if win_rate else "N/A",
                        "peak_date": peak_date,
                        "valley_date": valley_date,
                        "composite_return": comp_ret,
                    })

                df_display = pd.DataFrame(data)
                display_cols = ["形态", "位置", "匹配日期", "收盘价", "历史样本", "历史平均收益", "历史胜率"]
                st.dataframe(df_display[display_cols], width='stretch')

                # 加载K线数据（与诊断窗口日期范围一致）
                market_data = load_data(
                    source='freestockdb',
                    tickers=[selected_code],
                    start=start_date.strftime("%Y-%m-%d"),
                    end=end_date.strftime("%Y-%m-%d")  # 与诊断窗口一致
                )
                ohlc = market_data.get_ohlc(selected_code)

                if ohlc is None or ohlc.empty:
                    st.warning("无法加载K线数据，跳过绘图")
                    conn.close()
                    return

                st.subheader("📈 K线图（形态标注）")

                # 准备空的交易记录
                empty_trades = pd.DataFrame(columns=['Date', 'Stock', 'Action', 'Price', 'Shares'])

                # 复用 plot_kline_with_trades 绘制基础K线
                fig = plot_kline_with_trades(ohlc, empty_trades, selected_code, selected_name)

                # ---- 叠加形态标记（简化样式，减少渲染负荷） ----
                pattern_marks = []
                for _, row in df_display.iterrows():
                    pattern_marks.append({
                        'date': row['匹配日期'],
                        'price': row['收盘价'],
                        'label': row['形态'],
                        'band_pos': row['位置'],
                        'peak_date': row['peak_date'],
                        'valley_date': row['valley_date'],
                    })

                for mark in pattern_marks:
                    mark_date = pd.to_datetime(mark['date']).normalize()
                    color = 'green' if mark['band_pos'] in ['rise_lower', 'fall_lower', 'valley'] else 'red'
                    # 标记点大小缩小到8
                    fig.add_trace(go.Scatter(
                        x=[mark_date],
                        y=[mark['price']],
                        mode='markers+text' if show_labels else 'markers',
                        marker=dict(
                            symbol='triangle-up' if mark['band_pos'] in ['rise_lower', 'fall_lower', 'valley'] else 'triangle-down',
                            size=8,  # 缩小
                            color=color,
                            line=dict(width=0.5, color='white')
                        ),
                        text=[mark['label']] if show_labels else None,
                        textposition='top center',
                        textfont=dict(size=8, color='black'),
                        name=f"{mark['label']} @ {mark['band_pos']}",
                        showlegend=False
                    ))

                fig.update_layout(
                    title=f"{selected_code} {selected_name} K线图（形态标注）",
                    height=700,
                    hovermode='x unified',
                    xaxis=dict(rangeslider_visible=True)
                )

                st.plotly_chart(fig, width='stretch')

                # ---- 历史统计汇总 ----
                st.subheader("📊 历史统计汇总（该股票所有 ready 记录）")
                cursor.execute("""
                    SELECT pattern_name, band_position,
                           COUNT(*) as cnt,
                           AVG(composite_return) as avg_ret,
                           SUM(CASE WHEN composite_return > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate
                    FROM pattern_history
                    WHERE symbol = ?
                      AND band_position_ready = 1
                      AND composite_return IS NOT NULL
                    GROUP BY pattern_name, band_position
                    ORDER BY cnt DESC
                    LIMIT 30
                """, (selected_code,))

                stats_rows = cursor.fetchall()
                if stats_rows:
                    stats_data = []
                    for sr in stats_rows:
                        stats_data.append({
                            "形态": sr[0],
                            "位置": sr[1],
                            "样本量": sr[2],
                            "平均收益": f"{sr[3]:.2%}" if sr[3] is not None else "N/A",
                            "胜率": f"{sr[4]:.0%}" if sr[4] is not None else "N/A",
                        })
                    st.dataframe(pd.DataFrame(stats_data), width='stretch')
                else:
                    st.caption("暂无历史统计数据")

                conn.close()

            except Exception as e:
                st.error(f"诊断失败: {str(e)}")
                import traceback
                st.code(traceback.format_exc())


# ==================== 主入口 ====================
if mode == "📈 回测":
    run_backtest()
elif mode == "🔍 形态诊断":
    run_pattern_diagnosis()
else:
    run_data_viewer()