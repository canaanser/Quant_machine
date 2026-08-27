# -*- coding: utf-8 -*-
"""
大样本信号复核（2026-08-28 小二陈）

用法（Windows 上，项目根目录）：
    python scripts/verify_signals.py

用全库（104 只 × 10 年，368409 条）复核之前的小样本结论：
  一、乌云盖顶：冷却期 × 回撤深度 → 5日收益/胜率 矩阵
      （之前小样本：冷却30天+中跌 → D+5 +7.4%，66%胜率，38样本）
  二、首现效应：首现 vs 非首现 → 胜率/收益（之前小样本：首现60-65%胜率）
  三、冷却分档普适性：全部形态按冷却分档

数据源：扫描器已算好的 cooldown_days（NULL=首现）/ drawdown_from_peak（120日回撤）
        / return_5d（事后验证用，不做回测决策）
"""
import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB = PROJECT_ROOT / "data" / "index_store" / "pattern_history.db"

DARK_CLOUD = "2_bearish_0_dark_cloud"


def load():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = conn.execute("""
        SELECT symbol, pattern_id, substr(match_date,1,10),
               return_5d, cooldown_days, drawdown_from_peak
        FROM pattern_history WHERE return_5d IS NOT NULL
    """).fetchall()
    conn.close()
    return rows


def gap_b(g):
    if g is None:
        return "首现"
    if g < 10:
        return "0-10天"
    if g < 30:
        return "10-30天"
    return "30天+"


def dd_b(dd):
    if dd is None:
        return "无回撤"
    if dd < -0.20:
        return "深跌>20%"
    if dd < -0.10:
        return "中跌10-20%"
    return "浅跌<10%"


def stat(name, lst):
    if not lst:
        return
    arr = np.array([r[3] for r in lst])
    print(f"{name:<12}{len(lst):>9}{np.mean(arr > 0):>8.1%}{np.mean(arr):>+9.2%}")


def main():
    rows = load()
    print(f"全库形态记录（有5日收益）: {len(rows)} 条")

    # ===== 一、乌云盖顶 冷却×处境 矩阵 =====
    dc = [r for r in rows if r[1] == DARK_CLOUD]
    print(f"\n{'='*60}\n一、乌云盖顶：冷却 × 回撤 → 5日收益/胜率（全库 {len(dc)} 条）\n{'='*60}")
    matrix = defaultdict(list)
    for sym, pid, dt, r5, cd, dd in dc:
        matrix[(gap_b(cd), dd_b(dd))].append(r5)
    print(f"{'冷却':<10}{'处境':<12}{'样本':>6}{'胜率':>7}{'5日均':>9}")
    for gb in ["首现", "0-10天", "10-30天", "30天+"]:
        for db in ["深跌>20%", "中跌10-20%", "浅跌<10%"]:
            lst = matrix.get((gb, db), [])
            if len(lst) >= 3:
                arr = np.array(lst)
                print(f"{gb:<10}{db:<12}{len(lst):>6}{np.mean(arr > 0):>6.0%}{np.mean(arr):>+8.2%}")

    # ===== 二、首现效应（全部形态） =====
    print(f"\n{'='*60}\n二、首现效应（全部形态，cooldown IS NULL = 首现）\n{'='*60}")
    print(f"{'分组':<12}{'样本':>9}{'胜率':>8}{'5日均':>9}")
    stat("首现", [r for r in rows if r[4] is None])
    stat("非首现", [r for r in rows if r[4] is not None])

    # ===== 三、冷却分档（全部形态） =====
    print(f"\n{'='*60}\n三、冷却分档普适性（全部形态）\n{'='*60}")
    for gb in ["0-10天", "10-30天", "30天+"]:
        stat(gb, [r for r in rows if r[4] is not None and gap_b(r[4]) == gb])

    # ===== 四、关键信号：冷却30天+ × 中跌 的乌云盖顶（对比全部乌云盖顶） =====
    print(f"\n{'='*60}\n四、目标信号对比（冷却30天+中跌的乌云盖顶）\n{'='*60}")
    key = [(r[3]) for r in dc if r[4] is not None and r[4] >= 30
           and r[5] is not None and -0.20 <= r[5] < -0.10]
    if key:
        arr = np.array(key)
        print(f"冷却30天+中跌乌云盖顶: 样本={len(arr)} 胜率={np.mean(arr > 0):.1%} 5日均={np.mean(arr):+.2%}")
    print("全部乌云盖顶:")
    if dc:
        arr = np.array([r[3] for r in dc])
        print(f"  样本={len(arr)} 胜率={np.mean(arr > 0):.1%} 5日均={np.mean(arr):+.2%}")

    print("\n✅ 完成。判定：目标信号胜率显著高于全部乌云盖顶且样本大 → 结论在大样本下成立")


if __name__ == "__main__":
    main()
