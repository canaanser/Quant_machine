"""
波段识别器
分形法识别波峰/谷底，配对输出有效波段
"""

from typing import List, Dict
import pandas as pd


def detect_waves(
    df: pd.DataFrame,
    window_days: int = 150,
    lookback: int = 5,
    min_amplitude: float = 0.08
) -> List[Dict]:
    """
    识别有效波段（峰→谷 或 谷→峰）

    输入：
        df: 标准 OHLCV DataFrame（含 open/high/low/close/volume，日期索引）
        window_days: 扫描窗口（默认150天）
        lookback: 峰谷识别回看窗口（默认5）
        min_amplitude: 最小振幅（默认8%）

    输出：
        [{
            "peak_date": "2026-06-15",
            "peak_price": 36.50,
            "valley_date": "2026-07-10",
            "valley_price": 34.02,
            "amplitude": 0.068,
            "direction": "down"   # "down" 峰→谷 / "up" 谷→峰
        }, ...]
    """
    if df.empty or len(df) < lookback * 2 + 1:
        return []

    # 取最近 window_days 条数据
    data = df.tail(window_days).reset_index(drop=True)

    # 确保列名标准
    if 'high' not in data.columns or 'low' not in data.columns:
        raise KeyError("DataFrame 必须包含 'high' 和 'low' 列")

    # 提取日期列（如果存在），否则使用索引
    date_series = None
    if 'date' in data.columns:
        date_series = data['date']
    elif df.index.name == 'date' or isinstance(df.index, pd.DatetimeIndex):
        # 如果原df的索引是日期，使用索引
        date_series = df.tail(window_days).index
    else:
        # 否则使用整数索引
        date_series = data.index

    # 将日期统一转换为字符串
    def to_date_str(val):
        if hasattr(val, 'strftime'):
            return val.strftime('%Y-%m-%d')
        elif isinstance(val, pd.Timestamp):
            return val.strftime('%Y-%m-%d')
        else:
            return str(val)

    # ---- 1. 识别波峰和谷底 ----
    peaks = []
    valleys = []

    for i in range(lookback, len(data) - lookback):
        left_lows = data['low'].iloc[i - lookback:i]
        right_lows = data['low'].iloc[i + 1:i + lookback + 1]
        is_valley = (data['low'].iloc[i] <= left_lows.min() and
                     data['low'].iloc[i] <= right_lows.min())

        left_highs = data['high'].iloc[i - lookback:i]
        right_highs = data['high'].iloc[i + 1:i + lookback + 1]
        is_peak = (data['high'].iloc[i] >= left_highs.max() and
                   data['high'].iloc[i] >= right_highs.max())

        # 获取日期
        current_date = date_series[i] if date_series is not None else data.index[i]
        date_str = to_date_str(current_date)

        if is_valley:
            valleys.append({
                "type": "valley",
                "idx": i,
                "date": date_str,
                "price": data['low'].iloc[i]
            })
        elif is_peak:
            peaks.append({
                "type": "peak",
                "idx": i,
                "date": date_str,
                "price": data['high'].iloc[i]
            })

    # ---- 2. 配对：按顺序交替配对峰谷 ----
    points = sorted(peaks + valleys, key=lambda x: x['idx'])

    # 过滤连续同类，取更极端的那个
    filtered = []
    for p in points:
        if not filtered or filtered[-1]['type'] != p['type']:
            filtered.append(p)
        else:
            # 同类型取更极端的
            if p['type'] == 'peak' and p['price'] > filtered[-1]['price']:
                filtered[-1] = p
            elif p['type'] == 'valley' and p['price'] < filtered[-1]['price']:
                filtered[-1] = p

    # 配对（峰→谷 或 谷→峰）
    waves = []
    for i in range(len(filtered) - 1):
        prev = filtered[i]
        curr = filtered[i + 1]
        if prev['type'] == curr['type']:
            continue

        if prev['type'] == 'peak':
            amp = (prev['price'] - curr['price']) / prev['price']
            direction = "down"
            peak, valley = prev, curr
        else:  # valley → peak
            amp = (curr['price'] - prev['price']) / prev['price']
            direction = "up"
            peak, valley = curr, prev

        if amp >= min_amplitude:
            waves.append({
                "peak_date": peak['date'],
                "peak_price": peak['price'],
                "valley_date": valley['date'],
                "valley_price": valley['price'],
                "amplitude": round(amp, 4),
                "direction": direction
            })

    return waves