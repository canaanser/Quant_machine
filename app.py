# -*- coding: utf-8 -*-
"""
量化回测系统前端入口（2026-08-26 小二陈：拆分为 views/ 页面层 + utils/ 工具层）
本文件只保留：页面配置、侧边栏路由、页面分发。
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

import streamlit as st

from views.backtest_view import run_backtest
from views.data_viewer import run_data_viewer
from views.pattern_diagnosis import run_pattern_diagnosis

st.set_page_config(page_title="量化回测系统", layout="wide")

if 'initial_cash_memory' not in st.session_state:
    st.session_state.initial_cash_memory = 500000

st.title("📊 量化选股回测系统（Alpha剥离流水线）")

mode = st.sidebar.radio(
    "选择功能",
    ["📈 回测", "📋 数据查看", "🔍 形态诊断"],
    index=0
)

# ===== 页面分发 =====
if mode == "📈 回测":
    run_backtest()
elif mode == "📋 数据查看":
    run_data_viewer()
elif mode == "🔍 形态诊断":
    run_pattern_diagnosis()
