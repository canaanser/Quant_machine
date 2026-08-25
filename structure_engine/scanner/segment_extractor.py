"""
片段截取器 - 修复版
兼容中英文列名
"""
from typing import List, Dict, Optional, Any
import pandas as pd


class Segment:
    def __init__(self, valley_buy: dict, peak_sell: dict, valley_confirm: dict,
                 kline_data: pd.DataFrame, ma_data: pd.DataFrame,
                 best_buy: dict, best_sell: dict,
                 ma_buy: Optional[dict], ma_sell: Optional[dict]):
        self.valley_buy = valley_buy
        self.peak_sell = peak_sell
        self.valley_confirm = valley_confirm
        self.kline_data = kline_data
        self.ma_data = ma_data
        self.best_buy = best_buy
        self.best_sell = best_sell
        self.ma_buy = ma_buy
        self.ma_sell = ma_sell
        self.symbol = None
        self.file_path = None
        self.start_row = valley_buy.get('idx', 0)
        self.end_row = valley_confirm.get('idx', 0)

    def to_dict(self) -> dict:
        return {
            "valley_buy": self.valley_buy,
            "peak_sell": self.peak_sell,
            "valley_confirm": self.valley_confirm,
            "best_buy": self.best_buy,
            "best_sell": self.best_sell,
            "ma_buy": self.ma_buy,
            "ma_sell": self.ma_sell,
            "start_row": self.start_row,
            "end_row": self.end_row,
            "amplitude": (self.peak_sell['price'] - self.valley_buy['price']) / self.valley_buy['price'],
            "duration": self.valley_confirm.get('idx', 0) - self.valley_buy.get('idx', 0),
        }


def find_golden_cross(df: pd.DataFrame, start_idx: int, end_idx: int) -> Optional[dict]:
    """在指定区间内查找金叉（MA5上穿MA20）"""
    if 'MA5' not in df.columns or 'MA20' not in df.columns:
        return None
    data = df.iloc[start_idx:end_idx+1]
    for i in range(1, len(data)):
        if data.iloc[i-1]['MA5'] <= data.iloc[i-1]['MA20'] and data.iloc[i]['MA5'] > data.iloc[i]['MA20']:
            close_price = data.iloc[i].get('close', data.iloc[i].get('收盘价', 0))
            return {"date": data.index[i], "price": close_price}
    return None


def find_death_cross(df: pd.DataFrame, start_idx: int, end_idx: int) -> Optional[dict]:
    """在指定区间内查找死叉（MA5下穿MA20）"""
    if 'MA5' not in df.columns or 'MA20' not in df.columns:
        return None
    data = df.iloc[start_idx:end_idx+1]
    for i in range(1, len(data)):
        if data.iloc[i-1]['MA5'] >= data.iloc[i-1]['MA20'] and data.iloc[i]['MA5'] < data.iloc[i]['MA20']:
            close_price = data.iloc[i].get('close', data.iloc[i].get('收盘价', 0))
            return {"date": data.index[i], "price": close_price}
    return None


def extract_segments(
    waves: List[dict],
    df: pd.DataFrame,
    min_amplitude: float = 0.08,
    symbol: str = "",
    file_path: str = ""
) -> List[Segment]:
    if len(waves) < 3:
        return []

    segments = []

    for i in range(len(waves) - 2):
        if waves[i]['type'] == 'valley' and waves[i+1]['type'] == 'peak' and waves[i+2]['type'] == 'valley':
            valley_buy = waves[i]
            peak_sell = waves[i+1]
            valley_confirm = waves[i+2]

            amplitude = (peak_sell['price'] - valley_buy['price']) / valley_buy['price']
            if amplitude < min_amplitude:
                continue

            start_idx = valley_buy['idx']
            end_idx = valley_confirm['idx']

            kline_data = df.iloc[start_idx:end_idx+1].copy()
            ma_data = df.iloc[start_idx:end_idx+1][['MA5', 'MA10', 'MA20', 'MA60']].copy() if all(c in df.columns for c in ['MA5','MA10','MA20','MA60']) else pd.DataFrame()

            ma_buy = find_golden_cross(df, start_idx, end_idx)
            ma_sell = find_death_cross(df, start_idx, end_idx)

            segment = Segment(
                valley_buy=valley_buy,
                peak_sell=peak_sell,
                valley_confirm=valley_confirm,
                kline_data=kline_data,
                ma_data=ma_data,
                best_buy=valley_buy,
                best_sell=peak_sell,
                ma_buy=ma_buy,
                ma_sell=ma_sell,
            )
            segment.symbol = symbol
            segment.file_path = file_path

            segments.append(segment)

    return segments