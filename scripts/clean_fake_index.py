# -*- coding: utf-8 -*-
"""清理误扫的"假指数"股票（2026-08-28）
stockdb 无指数数据，--pool index 扫进的是 4 只股票（000016深康佳A/000688国城矿业/
000852石化机械/000905厦门港务）——删除其 pattern/wave/atomic/scan_progress 数据。
用法（Windows）：python scripts/clean_fake_index.py
"""
import sqlite3
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
DB = PROJECT / "data" / "index_store" / "pattern_history.db"
FAKE = ('000016', '000688', '000852', '000905')


def main():
    conn = sqlite3.connect(str(DB))
    for t in ('pattern_history', 'wave_history', 'atomic_features', 'scan_progress'):
        cur = conn.execute(
            f'DELETE FROM {t} WHERE symbol IN ({"?," * (len(FAKE) - 1)}?)', FAKE)
        print(f'{t}: 删除 {cur.rowcount} 条')
    conn.commit()
    conn.close()
    print('✅ 假指数股票已清理')


if __name__ == "__main__":
    main()
