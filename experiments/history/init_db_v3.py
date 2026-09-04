# -*- coding: utf-8 -*-
"""
新库建库脚本 V3.0（2026-08-27 小二陈）
=============================================
创建 pattern_history_v3.db（独立新库，不覆盖旧库），按 schema_v3 建表。
旧库 pattern_history.db 保留作备份。

用法（Windows / WSL 均可）：
    python scripts/init_db_v3.py
"""
import sys
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from structure_engine.scanner.data_writer.schema_v3 import (
    ALL_CREATES, INDEXES,
)

NEW_DB = PROJECT_ROOT / "data" / "index_store" / "pattern_history_v3.db"


def main():
    NEW_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(NEW_DB))
    cur = conn.cursor()

    for ddl in ALL_CREATES:
        cur.execute(ddl)
    for idx in INDEXES:
        cur.execute(idx)

    conn.commit()

    # 验证
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    print(f"✅ 新库已创建: {NEW_DB}")
    print(f"   表: {tables}")

    # 各表字段数
    for t in tables:
        ncols = len(cur.execute(f"PRAGMA table_info({t})").fetchall())
        print(f"   - {t}: {ncols} 列")

    conn.close()
    print("\n✅ 建库完成。旧库 pattern_history.db 未动（保留备份）。")


if __name__ == "__main__":
    main()
