"""
因子调制器 (Factor Modulator)
职责：每日输出因子调制系数（modulator），默认全返回 1.0
数据结构支持"只增不减"的演进策略
"""

import pandas as pd


class FactorModulator:
    """
    因子调制器
    当前版本：全部返回 1.0（未定义因子）
    未来可扩展为根据因子值动态调整
    """
    
    def __init__(self):
        # 未来可在此加载因子配置
        pass
    
    def get_modulator(self, date: str, symbol: str, factors: dict = None) -> float:
        """
        获取指定日期和股票的因子调制系数
        未定义因子返回 1.0
        """
        # 当前版本：全返回 1.0
        return 1.0
    
    def get_factor_table(self, date: str, symbols: list) -> pd.DataFrame:
        """
        批量获取因子调制系数表
        返回: DataFrame with columns [date, symbol, modulator, tags]
        """
        data = []
        for symbol in symbols:
            data.append({
                'date': date,
                'symbol': symbol,
                'modulator': 1.0,
                'tags': []  # 可存放标签信息
            })
        return pd.DataFrame(data)

    def get_market_trend(self, benchmark_price: pd.Series, ma_period: int = 20) -> float:
        """
        计算大盘趋势因子
        :param benchmark_price: 大盘收盘价序列
        :param ma_period: MA周期（默认20）
        :return: 1.0（向上）, 0.0（向下）
        """
        if benchmark_price is None or benchmark_price.empty or len(benchmark_price) < ma_period + 1:
            return 1.0
        ma = benchmark_price.rolling(ma_period).mean()
        if len(ma) < 2:
            return 1.0
        if ma.iloc[-1] > ma.iloc[-2]:
            return 1.0
        else:
            return 0.0
