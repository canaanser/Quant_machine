# ============================================================
# Quant_Alpha_System — 一键复现开发/分析环境 (2026-09-07 老板拍板)
# ------------------------------------------------------------
# 用途: 在任意装 Docker 的机器上还原"纯 Python 分析环境 + 代码 + 依赖",
#       解决"依赖/环境/配置"一键搞定。clone 仓库后 docker build 即得。
#
# ⚠️ 重要边界(与 stockdb 的关系, 老板已认可):
#   - pybao/stockdb.pyd 是 Windows 二进制 → Linux 容器内装不上、import 即崩
#   - 本镜像 = 纯分析/研究环境: 只依赖 pandas/numpy/streamlit 的脚本直接跑
#   - 需要行情数据时走 HTTP 回退通道(core/data_loader/freestockdb.py 已内置:
#     import stock_sdk 失败 → 自动 HTTP 连宿主 127.0.0.1:7899)
#   - 权威回测(要 SDK qfq 口径)仍在 Windows 主机跑, 见 DECISIONS.md §3.8
#
# 用法:
#   docker build -t quant_alpha .
#   # 纯分析(不连行情):
#   docker run --rm -it quant_alpha bash
#   # 需要行情数据(宿主机已起 stockdb.exe):
#   docker run --rm -it --add-host=host.docker.internal:host-gateway quant_alpha bash
#     # 容器内脚本连 stockdb 用 host: host.docker.internal (见 core/data_loader 主机名可配)
# ============================================================

FROM python:3.12-slim

# 时区/地区(中文输出/日志)
ENV PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# 系统依赖(streamlit/matplotlib 等需要的底层库, 最小集)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# 1) 先装依赖(利用层缓存)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) 装 pybao 的纯 python 层(不含 .pyd); 有 .pyd 会崩, 排除
COPY config ./config
COPY core ./core
COPY selection ./selection
COPY utils ./utils
COPY scripts ./scripts
COPY experiments ./experiments
COPY pybao/stock_sdk.py ./pybao/
COPY data/tickers ./data/tickers
COPY tests ./tests

# stock_sdk.py 顶部 `from stockdb import *` 在容器内会 ImportError；
# core/data_loader 已捕获该异常自动回退 HTTP（见 freestockdb.fetch_daily_qfq_single），
# 因此这里刻意不提供 stockdb 占位模块——import 失败正是触发 HTTP 回退的开关。

CMD ["bash"]
