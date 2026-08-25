"""
信号调制器 (Signal Modulator)
职责：将策略原始评分与因子调制系数相乘，得到最终评分
"""

import pandas as pd


class SignalModulator:
    """
    信号调制器
    将 raw_score × modulator = final_score
    """
    
    def __init__(self):
        pass
    
    def modulate(self, raw_score: float, modulator: float) -> float:
        """
        调制单个信号
        """
        return raw_score * modulator
    
    def modulate_batch(self, signals: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
        """
        批量调制信号
        signals: DataFrame with columns [date, symbol, raw_score, ...]
        factors: DataFrame with columns [date, symbol, modulator, ...]
        返回: 添加了 final_score 列的信号表
        """
        result = signals.copy()
        # 合并因子数据
        merged = result.merge(factors, on=['date', 'symbol'], how='left')
        merged['modulator'] = merged.get('modulator', 1.0).fillna(1.0)
        merged['final_score'] = merged['raw_score'] * merged['modulator']
        
        # 保留原始列 + final_score
        if 'final_score' in result.columns:
            result['final_score'] = merged['final_score']
        else:
            result = result.assign(final_score=merged['final_score'])
        
        return result

    def modulate_with_market(self, signals: pd.DataFrame, market_trend: float) -> pd.DataFrame:
        """
        根据大盘趋势调制信号
        :param signals: 信号表 (含 raw_score)
        :param market_trend: 大盘趋势因子 (1=向上, 0=向下)
        :return: 调制后的信号表
        """
        result = signals.copy()
        if 'raw_score' in result.columns:
            result['final_score'] = result['raw_score'] * market_trend
        else:
            result['final_score'] = result.get('final_score', 0) * market_trend
        return result
