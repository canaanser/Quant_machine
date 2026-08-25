import sqlite3
from pathlib import Path

# 获取项目根目录（当前文件在 tests/ 下，父目录是项目根）
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "tests" / "data" / "index_store" / "pattern_history.db"

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

cursor.execute("""
    SELECT band_position, 
           COUNT(*) as cnt, 
           AVG(composite_return) as avg_ret,
           SUM(CASE WHEN composite_return > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate
    FROM pattern_history
    WHERE pattern_id = '1_neutral_0_doji' 
      AND band_position_ready = 1 
      AND composite_return IS NOT NULL
    GROUP BY band_position
    ORDER BY cnt DESC
""")

rows = cursor.fetchall()
print("位置 | 样本量 | 平均收益 | 胜率")
print("-" * 50)
for r in rows:
    print(f"{r[0]} | {r[1]} | {r[2]:.2%} | {r[3]:.0%}")

conn.close()