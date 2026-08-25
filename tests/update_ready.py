import sqlite3

conn = sqlite3.connect('data/index_store/pattern_history.db')
cursor = conn.cursor()

cursor.execute("""
    UPDATE pattern_history 
    SET band_position_ready = 1 
    WHERE band_position IS NOT NULL AND band_position != 'unknown'
""")
rows = cursor.rowcount
conn.commit()
conn.close()

print(f"✅ 更新了 {rows} 条记录")