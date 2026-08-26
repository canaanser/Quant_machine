# -*- coding: utf-8 -*-
"""回测页面（2026-08-26 小二陈：从 app.py 拆出）"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

from core import load_data, AlphaScoreStrategy, BacktestPipeline, metadata
from config.config import COMMISSION, LOOKBACK, TOP_N, WINDOW
from utils.kline_plotter import plot_kline_with_trades
from utils.stock_helpers import (DEBUG_MODE, init, rd, calc_single_stock_performance)

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
