"""
位置权重数据化（weight_estimator.py）
============================================
线C：从"拍脑袋权重表"过渡到"数据驱动权重表"。

方法：贝叶斯收缩估计（Bayesian Shrinkage）
  收缩均值 = (n × 格子均值 + κ × 全局均值) / (n + κ)
  - 格子样本少 → 权重趋近全局均值（不放大噪声）
  - 格子样本足 → 权重趋近格子真实均值

权重语义（与 WEIGHT_MAP 同格式）：
  - bullish 形态：位置收缩收益越高 → 权重越高（看涨信号在该位置越有效）
  - bearish 形态：位置收缩收益越负 → 权重越高（看跌信号在该位置越有效）
  - neutral 形态：|收缩收益| 越高 → 权重越高（该位置越有参考价值）
  归一化：该方向下所有位置中 |收缩收益| 最大值 → 1.0

用法：
  python -m structure_engine.cloud.weight_estimator        # 输出数据驱动权重表 + 对比
  from structure_engine.cloud.weight_estimator import estimate_weights
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict

# ===== 数据库路径（真实库） =====
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "index_store" / "pattern_history.db"

# 收缩强度（初始值，后续按数据积累调整）
KAPPA = 15.0

# 位置顺序（展示用）
POSITIONS = ["valley", "fall_lower", "fall_upper", "rise_lower", "rise_upper", "peak"]


def get_connection():
    return sqlite3.connect(str(DB_PATH))


def _pattern_direction(pattern_id: str) -> str:
    """从注册表取形态方向"""
    from structure_engine.morphology.registry import REGISTRY
    pat = REGISTRY.get(pattern_id)
    return pat.get("signal", "neutral") if pat else "neutral"


def estimate_weights(kappa: float = KAPPA) -> Dict[str, Dict[str, float]]:
    """
    从电子云格子统计生成数据驱动权重表。
    返回: {direction: {position: weight}}，格式与 signal_weights.WEIGHT_MAP 一致。
    """
    conn = get_connection()
    cur = conn.cursor()

    # 读取所有格子统计（排除 unknown）
    cur.execute("""
        SELECT i.pattern_id, i.band_position, d.mean_return, d.sample_count
        FROM electron_cloud_index i
        JOIN electron_cloud_distribution d ON d.distribution_id = i.distribution_id
        WHERE i.band_position != 'unknown' AND d.mean_return IS NOT NULL
    """)
    rows = cur.fetchall()
    conn.close()

    # 按 (direction, position) 聚合样本
    cells: Dict[str, Dict[str, list]] = {d: {p: [] for p in POSITIONS} for d in ["bullish", "bearish", "neutral"]}
    for pattern_id, position, mean_return, sample_count in rows:
        direction = _pattern_direction(pattern_id)
        if position not in POSITIONS:
            continue
        cells[direction][position].append((mean_return, sample_count))

    # 全局均值（所有格子样本加权）
    all_means = [(m, n) for d in cells.values() for pos_list in d.values() for m, n in pos_list]
    total_n = sum(n for _, n in all_means)
    global_mean = sum(m * n for m, n in all_means) / total_n if total_n > 0 else 0.0

    # 每个方向 × 位置：样本加权均值 + 收缩
    weights: Dict[str, Dict[str, float]] = {}
    for direction, pos_map in cells.items():
        shrunk = {}
        for position, samples in pos_map.items():
            if not samples:
                shrunk[position] = 0.0
                continue
            cell_n = sum(n for _, n in samples)
            cell_mean = sum(m * n for m, n in samples) / cell_n if cell_n > 0 else 0.0
            # 贝叶斯收缩
            shrunk[position] = (cell_n * cell_mean + kappa * global_mean) / (cell_n + kappa)

        # 归一化
        if direction == "bearish":
            base = [-s for s in shrunk.values()]          # 负收益大 → 权重高
        elif direction == "neutral":
            base = [abs(s) for s in shrunk.values()]      # |收益| 大 → 权重高
        else:
            base = list(shrunk.values())                   # 正收益大 → 权重高
        base = [max(0.0, b) for b in base]
        max_base = max(base) if base else 0.0
        if max_base <= 0:
            weights[direction] = {p: 0.0 for p in POSITIONS}
        else:
            weights[direction] = {p: round(b / max_base, 2) for p, b in zip(POSITIONS, base)}
    return weights


def compare_with_weigthmap(data_weights: Dict[str, Dict[str, float]]) -> None:
    """对比数据驱动权重表与现有 WEIGHT_MAP"""
    from structure_engine.signals.signal_weights import WEIGHT_MAP

    print("\n" + "=" * 90)
    print("数据驱动权重表 vs 现有 WEIGHT_MAP 对比")
    print("=" * 90)
    for direction in ["bullish", "bearish", "neutral"]:
        print(f"\n【{direction}】")
        print(f"  {'位置':<12} {'数据驱动':>8} {'现有WEIGHT_MAP':>14} {'差异':>8}")
        for pos in POSITIONS:
            dw = data_weights.get(direction, {}).get(pos, 0.0)
            ow = WEIGHT_MAP.get(direction, {}).get(pos, 0.0)
            diff = dw - ow
            flag = " ← 差异大" if abs(diff) >= 0.3 else ""
            print(f"  {pos:<12} {dw:>8.2f} {ow:>14.2f} {diff:>+8.2f}{flag}")


def save_weights_to_db(weights: Dict[str, Dict[str, float]], kappa: float = KAPPA, version: int = 1) -> bool:
    """
    数据驱动权重表落库（新表 signal_weight_table，带版本号）。
    现有 WEIGHT_MAP 保留不动——两个权重并存、可对比、可回退。
    查询时如需数据权重，从本表读取（按 version 取最新）。
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS signal_weight_table (
            direction TEXT NOT NULL,
            band_position TEXT NOT NULL,
            weight REAL NOT NULL,
            kappa REAL,
            version INTEGER,
            created_at TEXT,
            PRIMARY KEY (direction, band_position, version)
        )
    """)
    now = datetime.now().isoformat()
    for direction, pos_map in weights.items():
        for pos, w in pos_map.items():
            cur.execute("""
                INSERT OR REPLACE INTO signal_weight_table
                (direction, band_position, weight, kappa, version, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (direction, pos, float(w), kappa, version, now))
    conn.commit()
    conn.close()
    return True


def main():
    print("🚀 位置权重数据化（贝叶斯收缩，κ={:.0f}）...".format(KAPPA))
    weights = estimate_weights()
    print("\n=== 数据驱动权重表 ===")
    for direction, pos_map in weights.items():
        print(f"  {direction}: {pos_map}")
    compare_with_weigthmap(weights)

    # 权重表落库（版本 1）
    save_weights_to_db(weights, kappa=KAPPA, version=1)
    print("\n✅ 数据驱动权重表已落库 signal_weight_table（version=1，现有 WEIGHT_MAP 保留）")


if __name__ == "__main__":
    main()
