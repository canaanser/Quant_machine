# -*- coding: utf-8 -*-
"""形态诊断页面（2026-08-26 小二陈：从 app.py 拆出）"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core import load_data
from utils.kline_plotter import plot_kline_with_trades
from utils.stock_helpers import get_name_to_code

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
