# -*- coding: utf-8 -*-
"""
电子云（形态×位置 条件收益分布）验证脚本（2026-08-27 小二陈）

用法（Windows 上，项目根目录，建议扫描跑完后执行）：
    python scripts/verify_electron_cloud.py

输出：
  1. electron_cloud_distribution 表状态（组合数 / 样本量）
  2. 胜率最高/最低的组合 Top10
  3. 【对照】纯位置基准 vs 形态×位置：形态在位置内有没有增量信息
"""
import sys
import sqlite3
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "index_store" / "pattern_history.db"


def main():
    if not DB_PATH.exists():
        print(f"[错误] 库不存在: {DB_PATH}")
        return

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    # ---------- 1. distribution 表状态 ----------
    cols = [d[0] for d in conn.execute("SELECT * FROM electron_cloud_distribution LIMIT 0").description]
    rows = conn.execute("SELECT * FROM electron_cloud_distribution").fetchall()
    print("=" * 78)
    print("一、电子云分布表状态")
    print("=" * 78)
    print(f"列: {cols}")
    print(f"组合数: {len(rows)}")
    if not rows:
        print("⚠️ distribution 表为空——需先跑 builder 或重扫后重建电子云")
        return

    # 找胜率/均值列（兼容不同列名）
    def col(name, default=None):
        for c in cols:
            if name.lower() in c.lower():
                return c
        return default

    c_win = col("win", cols[0])
    c_mean = col("mean", col("avg", cols[1]))
    c_n = col("sample", col("count", cols[2]))
    c_pat = col("pattern", cols[3])
    c_pos = col("position", cols[4])

    # 按胜率排序
    def sortable(r):
        try:
            return float(r[cols.index(c_win)])
        except Exception:
            return 0.0

    ranked = sorted(rows, key=sortable, reverse=True)
    print(f"\n样本量分布: ", end="")
    try:
        ns = [r[cols.index(c_n)] for r in rows if r[cols.index(c_n)] is not None]
        if ns:
            print(f"min={min(ns)} max={max(ns)} 样本>=100的组合={sum(1 for n in ns if n >= 100)}")
    except Exception:
        print("(无法解析样本量列)")

    print(f"\n二、胜率 Top10（{c_pat} x {c_pos}）")
    print(f"{'形态':<20}{'位置':<12}{'样本':>7}{'胜率':>8}{'均值':>10}")
    print("-" * 60)
    for r in ranked[:10]:
        try:
            n = r[cols.index(c_n)]
            w = r[cols.index(c_win)]
            m = r[cols.index(c_mean)] if c_mean in cols else 0
            print(f"{str(r[cols.index(c_pat)]):<20}{str(r[cols.index(c_pos)]):<12}{n:>7}{float(w)*100 if w and w<=1 else w:>8.1f}{float(m):>10.4f}")
        except Exception as e:
            print("  (解析失败:", e, ")")

    print(f"\n三、胜率 Bottom10")
    print("-" * 60)
    for r in ranked[-10:]:
        try:
            n = r[cols.index(c_n)]
            w = r[cols.index(c_win)]
            m = r[cols.index(c_mean)] if c_mean in cols else 0
            print(f"{str(r[cols.index(c_pat)]):<20}{str(r[cols.index(c_pos)]):<12}{n:>7}{float(w)*100 if w and w<=1 else w:>8.1f}{float(m):>10.4f}")
        except Exception:
            pass

    # ---------- 3. 纯位置基准（对照） ----------
    print("\n" + "=" * 78)
    print("四、纯位置基准（pattern_history 按 band_position 分组）")
    print("=" * 78)
    try:
        base = conn.execute("""
            SELECT band_position,
                   COUNT(*) n,
                   AVG(return_5d) avg_r5,
                   SUM(CASE WHEN return_5d > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) win
            FROM pattern_history
            WHERE band_position IS NOT NULL AND band_position != 'unknown'
              AND return_5d IS NOT NULL
            GROUP BY band_position
            ORDER BY avg_r5 DESC
        """).fetchall()
        print(f"{'位置':<14}{'样本':>7}{'均值r5':>10}{'胜率':>8}")
        print("-" * 42)
        for bp, n, av, w in base:
            print(f"{str(bp):<14}{n:>7}{float(av):>10.4f}{float(w)*100:>7.1f}%")
        print("\n【判定】将二/三的组合胜率与四的纯位置胜率对比：")
        print("  组合胜率明显偏离其位置的基准胜率 → 形态有增量信息，电子云有价值")
        print("  组合胜率 ≈ 位置基准（相差<3个百分点）→ 形态无增量，电子云可降级为轻量模块")
    except Exception as e:
        print("纯位置基准计算失败:", e)

    conn.close()
    print("\n验证完毕。")


if __name__ == "__main__":
    main()
