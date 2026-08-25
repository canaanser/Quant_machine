"""
信号处置规则引擎：根据形态方向和波段位置，返回信号权重
权重为0时忽略信号，非0时乘以期望收益

权重来源（可切换，由 config.WEIGHT_SOURCE 控制）：
  'legacy' —— 下方 WEIGHT_MAP（经验设定，默认）
  'data'   —— 数据库 signal_weight_table（数据驱动，贝叶斯收缩生成）
"""

from pathlib import Path

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
    """返回信号权重，0表示忽略（legacy 表）"""
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


# ============================================================
# 数据驱动权重（signal_weight_table，贝叶斯收缩生成）
# ============================================================
_DATA_DB_PATH = Path(__file__).parent.parent.parent / "data" / "index_store" / "pattern_history.db"
_data_weights_cache = None


def _load_data_weights() -> dict:
    """从 signal_weight_table 加载最新版本数据驱动权重（带缓存）"""
    global _data_weights_cache
    if _data_weights_cache is not None:
        return _data_weights_cache
    w = {}
    try:
        import sqlite3
        conn = sqlite3.connect(str(_DATA_DB_PATH))
        cur = conn.cursor()
        cur.execute("""
            SELECT direction, band_position, weight FROM signal_weight_table
            WHERE version = (SELECT MAX(version) FROM signal_weight_table)
        """)
        for direction, position, weight in cur.fetchall():
            w.setdefault(direction, {})[position] = weight
        conn.close()
    except Exception:
        pass
    _data_weights_cache = w
    return w


def get_data_driven_weight(pattern_direction: str, band_position: str) -> float:
    """从数据驱动权重表取权重（0 表示忽略）"""
    return _load_data_weights().get(pattern_direction, {}).get(band_position, 0.5)


def get_weight(pattern_direction: str, band_position: str, source: str = 'legacy') -> float:
    """统一取权重入口：source='legacy' 用现有表 / 'data' 用数据驱动表"""
    if source == 'data':
        return get_data_driven_weight(pattern_direction, band_position)
    return get_signal_weight(pattern_direction, band_position)


def get_direction_weight(pattern_direction: str, source: str = 'legacy',
                         positions=('valley', 'fall_lower', 'fall_upper', 'rise_lower', 'rise_upper', 'peak')) -> float:
    """方向级权重：6 个位置权重的平均（回测中无波段位置信息时的降级方案）"""
    ws = [get_weight(pattern_direction, p, source) for p in positions]
    return sum(ws) / len(ws) if ws else 0.5


# 快速验证
if __name__ == "__main__":
    print("信号权重验证")
    print(f"bullish + valley = {get_signal_weight('bullish', 'valley')}")  # 1.0
    print(f"bullish + peak = {get_signal_weight('bullish', 'peak')}")      # 0.0
    print(f"bearish + valley = {get_signal_weight('bearish', 'valley')}")  # 0.0
    print(f"bearish + peak = {get_signal_weight('bearish', 'peak')}")      # 1.0
    print(f"中性信号在谷底 = {get_signal_weight('neutral', 'valley')}")    # 0.7
    print(f"忽略: bullish+peak = {is_signal_ignored('bullish', 'peak')}")  # True