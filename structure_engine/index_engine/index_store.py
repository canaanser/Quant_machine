"""
索引存储管理（SQLite）
"""
import sqlite3
import json
import hashlib
from typing import Optional, List, Dict, Any
from pathlib import Path


class IndexStore:
    def __init__(self, db_path: str = "data/index_store/index.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS index_records (
                index_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                segment_type TEXT,
                features TEXT,
                tags TEXT,
                best_buy TEXT,
                best_sell TEXT,
                ma_buy TEXT,
                ma_sell TEXT,
                data_pointer TEXT,
                forward_stats TEXT,
                amplitude REAL,
                duration INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol ON index_records(symbol)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_start_date ON index_records(start_date)
        """)

        conn.commit()
        conn.close()

    def insert(self, record: dict) -> str:
        index_id = record.get('index_id') or self._generate_id(record)

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO index_records (
                index_id, symbol, start_date, end_date, segment_type,
                features, tags, best_buy, best_sell, ma_buy, ma_sell,
                data_pointer, forward_stats, amplitude, duration
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            index_id,
            record.get('symbol', ''),
            record.get('start_date', ''),
            record.get('end_date', ''),
            record.get('segment_type', ''),
            json.dumps(record.get('features', {})),
            json.dumps(record.get('tags', [])),
            json.dumps(record.get('best_buy', {})),
            json.dumps(record.get('best_sell', {})),
            json.dumps(record.get('ma_buy', {})),
            json.dumps(record.get('ma_sell', {})),
            json.dumps(record.get('data_pointer', {})),
            json.dumps(record.get('forward_stats', {})),
            record.get('amplitude', 0.0),
            record.get('duration', 0)
        ))

        conn.commit()
        conn.close()
        return index_id

    def search(self, features: dict, tolerance: float = 0.15) -> List[dict]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        target_amp = features.get('amplitude', 0.08)
        target_duration = features.get('duration', 30)

        amp_low = target_amp * (1 - tolerance)
        amp_high = target_amp * (1 + tolerance)
        dur_low = target_duration * (1 - tolerance)
        dur_high = target_duration * (1 + tolerance)

        cursor.execute("""
            SELECT * FROM index_records
            WHERE amplitude BETWEEN ? AND ?
              AND duration BETWEEN ? AND ?
            ORDER BY amplitude
            LIMIT 100
        """, (amp_low, amp_high, dur_low, dur_high))

        results = []
        for row in cursor.fetchall():
            results.append({
                'index_id': row['index_id'],
                'symbol': row['symbol'],
                'start_date': row['start_date'],
                'end_date': row['end_date'],
                'segment_type': row['segment_type'],
                'features': json.loads(row['features']),
                'tags': json.loads(row['tags']),
                'best_buy': json.loads(row['best_buy']),
                'best_sell': json.loads(row['best_sell']),
                'ma_buy': json.loads(row['ma_buy']),
                'ma_sell': json.loads(row['ma_sell']),
                'data_pointer': json.loads(row['data_pointer']),
                'forward_stats': json.loads(row['forward_stats']),
                'amplitude': row['amplitude'],
                'duration': row['duration'],
            })

        conn.close()
        return results

    def get_by_id(self, index_id: str) -> Optional[dict]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM index_records WHERE index_id = ?", (index_id,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return {
            'index_id': row['index_id'],
            'symbol': row['symbol'],
            'start_date': row['start_date'],
            'end_date': row['end_date'],
            'segment_type': row['segment_type'],
            'features': json.loads(row['features']),
            'tags': json.loads(row['tags']),
            'best_buy': json.loads(row['best_buy']),
            'best_sell': json.loads(row['best_sell']),
            'ma_buy': json.loads(row['ma_buy']),
            'ma_sell': json.loads(row['ma_sell']),
            'data_pointer': json.loads(row['data_pointer']),
            'forward_stats': json.loads(row['forward_stats']),
            'amplitude': row['amplitude'],
            'duration': row['duration'],
        }

    def count(self) -> int:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM index_records")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def _generate_id(self, record: dict) -> str:
        raw = f"{record.get('symbol', '')}_{record.get('start_date', '')}_{record.get('end_date', '')}"
        hash_suffix = hashlib.md5(raw.encode()).hexdigest()[:6]
        return f"IDX_{hash_suffix}"
