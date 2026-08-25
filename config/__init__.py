"""
配置包
"""

from .risk_config import DEFAULT_RISK_CONFIG


# ---------- 从根目录 config.py 导入配置 ----------
# config.py
# 全局参数配置文件（所有模块统一从这里读取）

# ----- 策略参数 -----
WINDOW = 60              # 滚动回归窗口（过去多少天）
LOOKBACK = 20            # 残差动量回看天数
TOP_N = 10               # 每日持有股票数量

# ----- 回测参数 -----
COMMISSION = 0.001       # 双边手续费率（千分之一）
INITIAL_CASH = 500000       # 初始资金（归一化）

# ----- 数据参数 -----
START_DATE = "2020-01-01"   # 数据起始日期（默认值，前端可手动选更早）
END_DATE = "2025-01-01"     # 数据结束日期
