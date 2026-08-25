"""
评分计算器 - 对称对数变换
将收益率映射为有符号评分 [-1, 1] 和归一化评分 [0, 1]
定死参数：上限300%，下限-90%
"""

import math

# ===== 固定参数（定死，不动态调整） =====
R_MAX = 3.0      # 上限收益率 300%
R_MIN = -0.9     # 下限收益率 -90%


def signed_log_score(r: float) -> float:
    """
    对称对数变换：收益率 → 有符号评分 [-1, 1]
    
    输入：r 为小数形式（10% → 0.10）
    输出：[-1, 1] 范围内的有符号评分
    """
    # 硬截断
    if r > R_MAX:
        r = R_MAX
    elif r < R_MIN:
        r = R_MIN

    if r >= 0:
        return math.log(1 + r) / math.log(1 + R_MAX)
    else:
        return -math.log(1 + abs(r)) / math.log(1 + abs(R_MIN))


def calc_base_score(r: float) -> float:
    """
    归一化到 [0, 1]
    """
    signed = signed_log_score(r)
    return (signed + 1.0) / 2.0


def calc_composite_return(r5: float, r10: float, r20: float) -> float:
    """
    加权复合收益率
    权重固定：5日 0.3，10日 0.3，20日 0.4
    """
    return r5 * 0.3 + r10 * 0.3 + r20 * 0.4


# ===== 快速参考映射表（供调试/验证使用） =====
REFERENCE_MAP = {
    -0.90: {"signed": -1.000, "base": 0.000},
    -0.50: {"signed": -0.632, "base": 0.184},
    -0.10: {"signed": -0.149, "base": 0.427},
    0.00:  {"signed": 0.000,  "base": 0.333},
    0.10:  {"signed": 0.149,  "base": 0.573},
    0.30:  {"signed": 0.409,  "base": 0.709},
    0.50:  {"signed": 0.632,  "base": 0.816},
    1.00:  {"signed": 1.000,  "base": 1.000},
    3.00:  {"signed": 1.000,  "base": 1.000},
}