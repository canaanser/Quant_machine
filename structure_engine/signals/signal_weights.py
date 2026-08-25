"""
信号处置规则引擎：根据形态方向和波段位置，返回信号权重
权重为0时忽略信号，非0时乘以期望收益
"""

WEIGHT_MAP = {
    "bullish": {
        "valley": 1.0,
        "fall_lower": 0.9,
        "fall_upper": 0.6,
        "rise_lower": 0.5,
        "rise_upper": 0.3,
        "peak": 0.0,
        "ranging": 0.3,
        "unknown": 0.5,
    },
    "bearish": {
        "peak": 1.0,
        "rise_upper": 0.9,
        "rise_lower": 0.6,
        "fall_upper": 0.5,
        "fall_lower": 0.3,
        "valley": 0.0,
        "ranging": 0.3,
        "unknown": 0.5,
    },
    "neutral": {
        "valley": 0.7,
        "fall_lower": 0.6,
        "peak": 0.7,
        "rise_upper": 0.6,
        "rise_lower": 0.3,
        "fall_upper": 0.3,
        "ranging": 0.2,
        "unknown": 0.4,
    }
}


def get_signal_weight(pattern_direction: str, band_position: str) -> float:
    """返回信号权重，0表示忽略"""
    if pattern_direction not in WEIGHT_MAP:
        return 0.5
    return WEIGHT_MAP[pattern_direction].get(band_position, 0.5)


def is_signal_ignored(pattern_direction: str, band_position: str) -> bool:
    """判断信号是否应被忽略"""
    return get_signal_weight(pattern_direction, band_position) == 0.0


def get_signal_weights_for_position(band_position: str) -> dict:
    """获取某个位置下所有方向的权重"""
    return {
        direction: weights.get(band_position, 0.5)
        for direction, weights in WEIGHT_MAP.items()
    }


# 快速验证
if __name__ == "__main__":
    print("信号权重验证")
    print(f"bullish + valley = {get_signal_weight('bullish', 'valley')}")  # 1.0
    print(f"bullish + peak = {get_signal_weight('bullish', 'peak')}")      # 0.0
    print(f"bearish + valley = {get_signal_weight('bearish', 'valley')}")  # 0.0
    print(f"bearish + peak = {get_signal_weight('bearish', 'peak')}")      # 1.0
    print(f"中性信号在谷底 = {get_signal_weight('neutral', 'valley')}")    # 0.7
    print(f"忽略: bullish+peak = {is_signal_ignored('bullish', 'peak')}")  # True