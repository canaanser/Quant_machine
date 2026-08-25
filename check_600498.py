import sqlite3
from pathlib import Path

# 自动定位项目根目录（当前脚本在项目根目录下运行）
PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = Path("E:/stockgate/Quant_Alpha_System/data/index_store/pattern_history.db")

print(f"数据库路径: {DB_PATH}")
if not DB_PATH.exists():
    print("❌ 数据库文件不存在，请确认路径")
    exit()

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

symbol = '600498'

# 1. 检查该股票有多少条记录
cursor.execute("SELECT COUNT(*) FROM pattern_history WHERE symbol = ?", (symbol,))
total = cursor.fetchone()[0]
print(f"📊 总记录数: {total}")

if total == 0:
    print("❌ 没有烽火通信的记录，请先运行全量扫描")
    conn.close()
    exit()

# 2. 检查 ready 状态分布
cursor.execute("SELECT band_position_ready, COUNT(*) FROM pattern_history WHERE symbol = ? GROUP BY band_position_ready", (symbol,))
ready_stats = cursor.fetchall()
print("📊 ready 状态分布:", ready_stats)

# 3. 更新 ready 状态（位置已知且非 unknown）
cursor.execute("""
    UPDATE pattern_history 
    SET band_position_ready = 1 
    WHERE symbol = ? 
      AND band_position IS NOT NULL 
      AND band_position != 'unknown'
""", (symbol,))
updated = cursor.rowcount
conn.commit()
print(f"✅ 更新了 {updated} 条记录的 ready 状态")

# 4. 再次检查 ready 统计
cursor.execute("SELECT band_position_ready, COUNT(*) FROM pattern_history WHERE symbol = ? GROUP BY band_position_ready", (symbol,))
after_stats = cursor.fetchall()
print("📊 更新后 ready 状态分布:", after_stats)

# 5. 查询所有形态
cursor.execute("""
    SELECT DISTINCT pattern_id 
    FROM pattern_history 
    WHERE symbol = ? 
      AND band_position_ready = 1 
      AND composite_return IS NOT NULL
""", (symbol,))
pattern_ids = [row[0] for row in cursor.fetchall()]

if not pattern_ids:
    print("❌ 没有 ready 记录（composite_return 不为 NULL），请检查数据")
    conn.close()
    exit()

print("=" * 80)
print(f"📊 {symbol} 所有形态电子云统计（共 {len(pattern_ids)} 种形态）")
print("=" * 80)

for pattern_id in pattern_ids:
    cursor.execute("""
        SELECT band_position, 
               COUNT(*) as cnt, 
               AVG(composite_return) as avg_ret,
               SUM(CASE WHEN composite_return > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate
        FROM pattern_history
        WHERE symbol = ?
          AND pattern_id = ?
          AND band_position_ready = 1 
          AND composite_return IS NOT NULL
        GROUP BY band_position
        ORDER BY cnt DESC
    """, (symbol, pattern_id))

    rows = cursor.fetchall()
    if not rows:
        continue

    print(f"\n形态: {pattern_id}")
    print("-" * 60)
    print(f"{'位置':<15} {'样本量':>6} {'平均收益':>12} {'胜率':>8}")
    print("-" * 60)
    for r in rows:
        print(f"{r[0]:<15} {r[1]:>6} {r[2]:>11.2%} {r[3]:>7.0%}")
    print("-" * 60)

conn.close()