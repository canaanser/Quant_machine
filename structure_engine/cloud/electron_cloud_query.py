"""
电子云模型查询接口：输入形态ID + 位置，输出期望收益 × 权重
"""

import sqlite3
import json
from pathlib import Path
from typing import Dict, Optional

# ===== 统一数据库路径（与 data_writer.py 保持一致） =====
# 测试环境下数据库在 tests/data/index_store/pattern_history.db
DB_PATH = Path(__file__).parent.parent.parent / "tests" / "data" / "index_store" / "pattern_history.db"


def get_connection():
    """获取数据库连接"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(DB_PATH))


def query_distribution(pattern_id: str, band_position: str) -> Optional[Dict]:
    """
    查询指定形态在指定位置的历史收益分布
    优先从 pattern_history 中 ready 记录统计，回退到 electron_cloud_distribution 表
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. 从 pattern_history 查询 ready 记录的收益分布（手动计算标准差）
    cursor.execute("""
        SELECT 
            COUNT(*) as sample_count,
            AVG(composite_return) as mean_return,
            SUM(composite_return * composite_return) as sum_sq,
            SUM(CASE WHEN composite_return > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as positive_ratio,
            MIN(composite_return) as min_return,
            MAX(composite_return) as max_return
        FROM pattern_history
        WHERE pattern_id = ?
          AND band_position = ?
          AND band_position_ready = 1
          AND composite_return IS NOT NULL
    """, (pattern_id, band_position))

    row = cursor.fetchone()
    conn.close()

    if row is None or row[0] == 0:
        # 没有 ready 记录，回退到 electron_cloud_distribution 表
        return query_from_cloud_table(pattern_id, band_position)

    sample_count = row[0]
    mean_return = row[1] if row[1] is not None else 0.0
    sum_sq = row[2] if row[2] is not None else 0.0
    positive_ratio = row[3] if row[3] is not None else 0.0

    # 计算标准差
    import math
    variance = max(0.0, (sum_sq / sample_count) - (mean_return * mean_return))
    std_return = math.sqrt(variance)

    return {
        "sample_list": [],
        "mean_return": mean_return,
        "std_return": std_return,
        "positive_ratio": positive_ratio,
        "sample_count": sample_count,
        "confidence_level": "high" if sample_count >= 20 else ("medium" if sample_count >= 5 else "low"),
        "min_return": row[4] if row[4] is not None else 0.0,
        "max_return": row[5] if row[5] is not None else 0.0,
    }


def query_from_cloud_table(pattern_id: str, band_position: str) -> Optional[Dict]:
    """
    从 electron_cloud_distribution 表查询（保留手工样本）
    """
    conn = get_connection()
    cursor = conn.cursor()

    grid_id = f"{pattern_id}_{band_position}"

    cursor.execute("""
        SELECT sample_list, mean_return, std_return, positive_ratio, sample_count
        FROM electron_cloud_distribution
        WHERE grid_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (grid_id,))

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    sample_list = json.loads(row[0]) if row[0] else []
    sample_count = row[4] if row[4] is not None else 0

    return {
        "sample_list": sample_list,
        "mean_return": row[1] if row[1] is not None else 0.0,
        "std_return": row[2] if row[2] is not None else 0.0,
        "positive_ratio": row[3] if row[3] is not None else 0.0,
        "sample_count": sample_count,
        "confidence_level": "high" if sample_count >= 20 else ("medium" if sample_count >= 5 else "low"),
    }


def query_electron_cloud(pattern_id: str, band_position: str) -> Dict:
    """
    查询电子云，返回最终的决策值
    """
    dist = query_distribution(pattern_id, band_position)

    if dist is None:
        return {
            "confidence": "low",
            "reason": "无样本数据",
            "decision_value": None,
            "sample_count": 0,
        }

    if dist["sample_count"] < 5:
        return {
            "confidence": "low",
            "reason": f"样本不足 ({dist['sample_count']} < 5)",
            "decision_value": None,
            "sample_count": dist["sample_count"],
        }

    return {
        "confidence": dist["confidence_level"],
        "sample_count": dist["sample_count"],
        "mean_return": dist["mean_return"],
        "std_return": dist["std_return"],
        "positive_ratio": dist["positive_ratio"],
        "decision_value": dist["mean_return"],
        "reason": "OK",
    }


def verify_query():
    """验证查询接口"""
    print("=" * 50)
    print("验证电子云查询接口")
    print("=" * 50)

    test_cases = [
        ("1_bullish_0_hammer", "valley"),
        ("1_bullish_0_hammer", "rise_lower"),
        ("2_bearish_0_shooting_star", "peak"),
        ("2_bearish_0_shooting_star", "rise_upper"),
        ("1_bullish_0_hammer", "peak"),  # 无样本
    ]

    for pattern_id, position in test_cases:
        result = query_electron_cloud(pattern_id, position)
        print(f"\n查询: {pattern_id} | {position}")
        print(f"   置信度: {result['confidence']}")
        if result.get('sample_count', 0) > 0:
            print(f"   样本量: {result['sample_count']}")
            print(f"   均值收益: {result.get('mean_return', 0):.2%}")
            print(f"   正收益比例: {result.get('positive_ratio', 0):.0%}")
            if result.get('decision_value') is not None:
                print(f"   决策值: {result['decision_value']:.2%}")
        else:
            print(f"   原因: {result.get('reason', '')}")


if __name__ == "__main__":
    verify_query()