"""
位置映射器：将形态日期映射到所在波段的进度值和位置标签
支持 pending 记录回填（波段闭合后更新 band_position）
"""

from typing import List, Dict, Optional, Any
import pandas as pd
from datetime import datetime


# 位置标签枚举
BAND_POSITIONS = {
    "valley": "谷底（波段绝对低点）",
    "rise_lower": "上升下段（上升趋势0-50%）",
    "rise_upper": "上升上段（上升趋势50-100%）",
    "peak": "峰顶（波段绝对高点）",
    "fall_upper": "下降上段（下降趋势0-50%）",
    "fall_lower": "下降下段（下降趋势50-100%）",
    "unknown": "位置未知（数据不足或波段未闭合）",
}


def map_position(match_date: str, match_price: float, waves: List[Dict]) -> Dict:
    """
    输入：形态匹配日期、匹配价格、该股票的波段列表
    输出：位置标签 + 进度值 + 波段方向
    """
    if not waves or not match_date:
        return {
            "band_position": "unknown",
            "band_progress": -1.0,
            "band_direction": "unknown"
        }

    match_date_str = str(match_date)[:10]

    for wave in waves:
        peak_date = wave.get('peak_date')
        valley_date = wave.get('valley_date')

        if not peak_date or not valley_date:
            continue

        # 确定波段的起止日期和价格
        if wave.get('direction') == 'down':
            start_date, start_price = peak_date, wave.get('peak_price')
            end_date, end_price = valley_date, wave.get('valley_price')
        else:  # up
            start_date, start_price = valley_date, wave.get('valley_price')
            end_date, end_price = peak_date, wave.get('peak_price')

        # 检查日期是否在波段范围内
        if start_date <= match_date_str <= end_date:
            # 计算进度 (0~1)
            total_range = abs(end_price - start_price)
            if total_range == 0:
                progress = 0.5
            else:
                if wave.get('direction') == 'down':
                    progress = (start_price - match_price) / total_range
                else:
                    progress = (match_price - start_price) / total_range
                progress = max(0.0, min(1.0, progress))

            # 映射位置标签
            if progress <= 0.02:
                position = "valley"
            elif progress >= 0.98:
                position = "peak"
            elif 0.02 < progress <= 0.5:
                position = "rise_lower" if wave.get('direction') == 'up' else "fall_upper"
            else:
                position = "rise_upper" if wave.get('direction') == 'up' else "fall_lower"

            return {
                "band_position": position,
                "band_progress": round(progress, 4),
                "band_direction": wave.get('direction', 'unknown')
            }

    # 未找到匹配波段
    return {
        "band_position": "unknown",
        "band_progress": -1.0,
        "band_direction": "unknown"
    }


def backfill_band_positions(
    symbol: str,
    wave: Dict,
    ohlc: pd.DataFrame,
    data_writer_module
) -> int:
    """
    当 wave_detector 识别到新的闭合波段后，
    回填该波段范围内所有 pending 记录的 band_position

    参数：
        symbol: 股票代码
        wave: 波段字典（含 peak_date, valley_date, direction, 起止日期）
        ohlc: 完整 OHLCV 数据（用于计算收益率和价格）
        data_writer_module: data_writer 模块（用于调用 get_pending_records_in_range 和 update_band_position）

    返回：
        更新的记录数
    """
    # 确定波段日期范围
    peak_date = wave.get('peak_date')
    valley_date = wave.get('valley_date')

    if not peak_date or not valley_date:
        return 0

    # 确定波段起止日期（按时间排序）
    if wave.get('direction') == 'down':
        start_date, end_date = valley_date, peak_date
    else:
        start_date, end_date = peak_date, valley_date

    # 确保日期顺序
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    # 1. 获取该波段范围内的 pending 记录
    pending_records = data_writer_module.get_pending_records_in_range(
        symbol, start_date, end_date
    )

    if not pending_records:
        return 0

    # 2. 构建波段列表（供 map_position 使用）
    waves = [wave]
    update_count = 0

    for record in pending_records:
        match_date = record['match_date']
        match_price = record['match_price']

        # 如果 match_price 缺失，从 ohlc 中获取
        if match_price is None or match_price == 0:
            try:
                if match_date in ohlc.index:
                    match_price = ohlc.loc[match_date, 'close']
                else:
                    match_date_dt = pd.to_datetime(match_date)
                    if match_date_dt in ohlc.index:
                        match_price = ohlc.loc[match_date_dt, 'close']
                    else:
                        continue
            except Exception:
                continue

        # 计算位置信息
        pos_info = map_position(match_date, match_price, waves)

        if pos_info['band_position'] == 'unknown':
            continue

        # 回填 band_position
        result = data_writer_module.update_band_position(
            record_id=record['record_id'],
            band_position=pos_info['band_position'],
            band_progress=pos_info['band_progress'],
            band_direction=pos_info['band_direction']
        )

        update_count += result

    return update_count


def locate_position_in_band(waves: List[Dict], match_date: str) -> Optional[Dict]:
    """
    定位某个日期在波段中的位置（仅用于查询，不写入数据库）
    返回：{"label": str, "progress": float, "direction": str}
    与 map_position 共享同一套映射逻辑
    """
    if not waves or not match_date:
        return None

    match_date_str = str(match_date)[:10]

    for wave in waves:
        peak_date = wave.get('peak_date')
        valley_date = wave.get('valley_date')

        if not peak_date or not valley_date:
            continue

        if wave.get('direction') == 'down':
            start_date, start_price = peak_date, wave.get('peak_price')
            end_date, end_price = valley_date, wave.get('valley_price')
        else:
            start_date, start_price = valley_date, wave.get('valley_price')
            end_date, end_price = peak_date, wave.get('peak_price')

        if not start_date or not end_date:
            continue

        if start_date <= match_date_str <= end_date:
            # 此时没有 match_price，无法计算精确 progress
            # 仅返回波段方向信息，由调用方决定如何使用
            return {
                "label": "unknown",
                "progress": 0.5,
                "direction": wave.get('direction', 'unknown')
            }

    return None


def is_position_ready(position_info: Dict) -> bool:
    """判断位置信息是否已确认（非 unknown）"""
    return position_info.get('band_position') not in (None, 'unknown')


def get_position_label(position_info: Dict) -> str:
    """获取位置标签的友好名称"""
    pos = position_info.get('band_position', 'unknown')
    return BAND_POSITIONS.get(pos, pos)