"""
专业级K线图绘制模块（稳定版 + 完整显示修复）
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd


def plot_kline_with_trades(price_data, trades_df, stock_code, stock_name=""):
    if price_data is None or price_data.empty:
        return go.Figure()
    
    required = ['open','high','low','close']
    if not all(c in price_data.columns for c in required):
        if 'close' in price_data.columns:
            price_data['open'] = price_data['close'].shift(1).fillna(price_data['close'])
            price_data['high'] = price_data[['open','close']].max(axis=1)
            price_data['low'] = price_data[['open','close']].min(axis=1)
        else:
            return go.Figure()
    
    if 'volume' not in price_data.columns:
        price_data['volume'] = 0
    
    price_data['MA5'] = price_data['close'].rolling(5).mean()
    price_data['MA10'] = price_data['close'].rolling(10).mean()
    price_data['MA20'] = price_data['close'].rolling(20).mean()
    price_data['MA60'] = price_data['close'].rolling(60).mean()
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.70, 0.30],
        subplot_titles=(f"{stock_code} {stock_name} 日K线图", "")
    )
    
    # 去掉周末空白
    for r in [1, 2]:
        fig.update_xaxes(
            rangebreaks=[dict(bounds=["sat", "mon"])],
            row=r, col=1
        )
    
    # ----- K线 -----
    fig.add_trace(go.Candlestick(
        x=price_data.index,
        open=price_data['open'],
        high=price_data['high'],
        low=price_data['low'],
        close=price_data['close'],
        name='K线',
        increasing_line_color='#E74C3C',
        decreasing_line_color='#2ECC71',
        showlegend=True
    ), row=1, col=1)
    
    # ----- 均线 -----
    fig.add_trace(go.Scatter(
        x=price_data.index, y=price_data['MA5'],
        mode='lines', name='MA5',
        line=dict(color='#FF6B6B', width=1.5),
        connectgaps=False
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=price_data.index, y=price_data['MA10'],
        mode='lines', name='MA10',
        line=dict(color='#FFA94D', width=1.5),
        connectgaps=False
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=price_data.index, y=price_data['MA20'],
        mode='lines', name='MA20',
        line=dict(color='#4ECDC4', width=1.5),
        connectgaps=False
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=price_data.index, y=price_data['MA60'],
        mode='lines', name='MA60',
        line=dict(color='#A29BFE', width=1.5),
        connectgaps=False
    ), row=1, col=1)
    
    # ----- 买卖点 -----
    if trades_df is not None and not trades_df.empty:
        buy_points = trades_df[trades_df['Action'] == 'BUY']
        sell_points = trades_df[trades_df['Action'] == 'SELL']
        
        if not buy_points.empty:
            buy_x = buy_points['Date']
            buy_y = buy_points['Price']
            fig.add_trace(go.Scatter(
                x=buy_x, y=buy_y,
                mode='markers',
                name='买入',
                marker=dict(
                    symbol='diamond',
                    size=8,
                    color='#E74C3C',
                    line=dict(width=1, color='#C0392B')
                ),
                hovertemplate='<b>买入</b><br>日期: %{x|%Y-%m-%d}<br>价格: %{y:.2f}<extra></extra>'
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=buy_x,
                y=buy_y * 1.03,
                mode='text',
                text=['<b>B</b>' for _ in range(len(buy_x))],
                textposition='middle center',
                textfont=dict(color='#E74C3C', size=8, family='Arial Black'),
                showlegend=False,
                hoverinfo='skip'
            ), row=1, col=1)
        
        if not sell_points.empty:
            sell_x = sell_points['Date']
            sell_y = sell_points['Price']
            fig.add_trace(go.Scatter(
                x=sell_x, y=sell_y,
                mode='markers',
                name='卖出',
                marker=dict(
                    symbol='diamond',
                    size=8,
                    color='#3498DB',
                    line=dict(width=1, color='#2980B9')
                ),
                hovertemplate='<b>卖出</b><br>日期: %{x|%Y-%m-%d}<br>价格: %{y:.2f}<extra></extra>'
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=sell_x,
                y=sell_y * 0.97,
                mode='text',
                text=['<b>S</b>' for _ in range(len(sell_x))],
                textposition='middle center',
                textfont=dict(color='#3498DB', size=8, family='Arial Black'),
                showlegend=False,
                hoverinfo='skip'
            ), row=1, col=1)
    
    # ----- 成交量 -----
    vol_colors = []
    for i in range(len(price_data)):
        if i == 0:
            vol_colors.append('#95A5A6')
        else:
            vol_colors.append('#E74C3C' if price_data['close'].iloc[i] >= price_data['close'].iloc[i-1] else '#2ECC71')
    
    fig.add_trace(go.Bar(
        x=price_data.index,
        y=price_data['volume'],
        name='成交量',
        marker_color=vol_colors,
        opacity=0.7,
        showlegend=False
    ), row=2, col=1)
    
    fig.update_yaxes(autorange=True, row=2, col=1, title_text="")
    
    # ----- 布局 -----
    fig.update_layout(
        template='plotly_white',
        height=700,
        showlegend=True,
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1,
            font=dict(size=10)
        ),
        hovermode='x unified',
        margin=dict(l=20, r=20, t=60, b=20),
        uirevision='constant',
        transition=dict(duration=0),
        autosize=False
    )
    
    # ----- 关键修复：强制显示全部数据范围 -----
    min_date = price_data.index.min()
    max_date = price_data.index.max()
    
    # 主图X轴（显示全部数据）
    fig.update_xaxes(
        type='date',
        tickangle=45,
        showgrid=True,
        gridcolor='rgba(200,200,200,0.3)',
        showticklabels=False,
        row=1, col=1,
        fixedrange=False,
        autorange=True,
        range=[min_date, max_date]  # 强制全量显示
    )
    
    # 副图X轴（带缩略图，同样全量）
    fig.update_xaxes(
        type='date',
        tickangle=45,
        showgrid=True,
        gridcolor='rgba(200,200,200,0.3)',
        row=2, col=1,
        fixedrange=False,
        autorange=True,
        range=[min_date, max_date],
        rangeslider=dict(
            visible=True,
            thickness=0.05,
            bgcolor='rgba(200,200,200,0.2)',
            range=[min_date, max_date]  # 缩略图初始化全量
        )
    )
    
    # Y轴
    fig.update_yaxes(
        title_text="价格",
        showgrid=True,
        gridcolor='rgba(200,200,200,0.3)',
        row=1, col=1,
        fixedrange=False,
        autorange=True
    )
    
    # 绘制早盘评分锚点（彩色三角）
    if 'early_score' in price_data.columns and not price_data['early_score'].isna().all():
        colors = price_data['early_score'].apply(lambda x: '#ef4444' if x > 0.6 else ('#22c55e' if x < 0.4 else '#94a3b8'))
        y_pos = price_data['high'].max() * 1.02
        fig.add_trace(go.Scatter(
            x=price_data.index,
            y=[y_pos] * len(price_data),
            mode='markers',
            marker=dict(size=14, color=colors, symbol='triangle-down', line=dict(width=1, color='white')),
            name='早盘评分',
            hovertemplate='日期: %{x}<br>早盘评分: %{text:.2f}<extra></extra>',
            text=price_data['early_score'].round(2),
            yaxis='y'
        ))
    
    return fig