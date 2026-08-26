# -*- coding: utf-8 -*-
"""
前端股票工具（2026-08-26 小二陈：从 app.py 拆出）
股票名称映射 / 类型判断 / 绩效计算 / 模拟评分 / SDK 检测 / 调试开关
"""

import numpy as np
import streamlit as st

# ===== 调试开关（前端） =====
DEBUG_MODE = True

# ===== free-stockdb SDK 检测 =====
try:
    from stock_sdk import rd, init, bk
    SDK_AVAILABLE = True
except ImportError:
    rd = init = bk = None
    SDK_AVAILABLE = False


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

