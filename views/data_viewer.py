# -*- coding: utf-8 -*-
"""数据查看页面（2026-08-26 小二陈：从 app.py 拆出）"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils.stock_helpers import get_name_to_code, SDK_AVAILABLE, init, rd

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
