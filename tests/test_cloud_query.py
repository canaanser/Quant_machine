"""
验证电子云查询接口（基于 pattern_history ready 记录）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from structure_engine.scanner.data_writer import DB_PATH
from structure_engine.cloud.electron_cloud_query import query_electron_cloud


def test_cloud_query():
    print("=" * 60)
    print("验证电子云查询接口（基于 ready 记录）")
    print("=" * 60)

    # 先查一下 pattern_history 里有哪些 ready 记录
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pattern_id, band_position, COUNT(*) as cnt
        FROM pattern_history
        WHERE band_position_ready = 1
        GROUP BY pattern_id, band_position
        ORDER BY cnt DESC
        LIMIT 10
    """)
    samples = cursor.fetchall()
    conn.close()

    if not samples:
        print("❌ 没有 ready 记录，请先运行全量扫描")
        return

    print("\n[1] ready 记录样本（前10组）:")
    for pid, pos, cnt in samples[:5]:
        print(f"    {pid} | {pos}: {cnt} 条")

    # 查询每个样本的电子云分布
    print("\n[2] 电子云查询结果:")
    for pid, pos, cnt in samples[:5]:
        result = query_electron_cloud(pid, pos)

        if result.get('reason') == '样本不足':
            print(f"    {pid} | {pos}: 样本不足 ({cnt} 条 < 5)，不参与统计")
            continue

        if result.get('decision_value') is None:
            print(f"    {pid} | {pos}: 无数据")
            continue

        print(f"    {pid} | {pos}:")
        print(f"        样本量: {result.get('sample_count', 0)}")
        print(f"        均值收益: {result.get('mean_return', 0):.2%}")
        print(f"        正收益比例: {result.get('positive_ratio', 0):.0%}")
        print(f"        置信度: {result.get('confidence', 'low')}")
        print(f"        决策值: {result.get('decision_value', 0):.2%}")

    print("\n" + "=" * 60)
    print("✅ 验证完成")
    print("=" * 60)


if __name__ == "__main__":
    test_cloud_query()