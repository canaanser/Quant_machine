import sqlite3
from pathlib import Path

DB = Path("data/index_store/pattern_history.db")
conn = sqlite3.connect(str(DB))
cursor = conn.cursor()

symbol = "000063"

print("=" * 60)
print(f"中兴通讯（{symbol}）近期 ready 形态记录")
print("=" * 60)

# 1. 查看 2026-07-01 之后的 ready 记录
cursor.execute("""
    SELECT match_date, pattern_name, band_position
    FROM pattern_history
    WHERE symbol = ?
      AND match_date >= '2026-07-01'
      AND band_position_ready = 1
    ORDER BY match_date
""", (symbol,))

rows = cursor.fetchall()
print(f"\n2026-07-01 之后 ready 形态共 {len(rows)} 条")
for r in rows[:20]:
    print(f"  {r[0]} | {r[1]} | 位置={r[2]}")

# 2. 查看最近30天的 ready 记录
cursor.execute("""
    SELECT MAX(match_date) FROM pattern_history
    WHERE symbol = ? AND band_position_ready = 1
""", (symbol,))
latest = cursor.fetchone()[0]
print(f"\n最近 ready 日期: {latest}")

conn.close()