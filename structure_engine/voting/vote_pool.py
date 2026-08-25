"""
投票池管理
"""
import json
import sqlite3
from typing import List, Dict, Any, Optional
from pathlib import Path


class VotePool:
    def __init__(self, db_path: str = "data/index_store/vote_pool.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vote_records (
                pattern_id TEXT PRIMARY KEY,
                total_score REAL DEFAULT 0,
                occurrence_count INTEGER DEFAULT 0,
                avg_score REAL DEFAULT 0,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                is_dormant INTEGER DEFAULT 0,
                dormancy_reason TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vote_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_id TEXT,
                date TEXT,
                score REAL,
                strength REAL,
                source TEXT,
                FOREIGN KEY (pattern_id) REFERENCES vote_records(pattern_id)
            )
        """)

        conn.commit()
        conn.close()

    def _get_connection(self):
        return sqlite3.connect(str(self.db_path))

    def add_vote(self, pattern_id: str, score: float, strength: float = 0.5, source: str = "scanner"):
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO vote_records (pattern_id, total_score, occurrence_count, avg_score)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(pattern_id) DO UPDATE SET
                total_score = total_score + ?,
                occurrence_count = occurrence_count + 1,
                avg_score = (total_score + ?) / (occurrence_count + 1),
                last_updated = CURRENT_TIMESTAMP
        """, (pattern_id, score, 1, score, score, score))

        cursor.execute("""
            INSERT INTO vote_history (pattern_id, date, score, strength, source)
            VALUES (?, date('now'), ?, ?, ?)
        """, (pattern_id, score, strength, source))

        conn.commit()
        conn.close()

    def get_rank(self, pattern_id: str) -> Optional[int]:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) + 1 FROM vote_records
            WHERE avg_score > (SELECT avg_score FROM vote_records WHERE pattern_id = ?)
        """, (pattern_id,))

        rank = cursor.fetchone()
        conn.close()
        return rank[0] if rank else None

    def get_top_n(self, n: int = 10, min_occurrences: int = 5) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM vote_records
            WHERE occurrence_count >= ? AND is_dormant = 0
            ORDER BY avg_score DESC
            LIMIT ?
        """, (min_occurrences, n))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def set_dormant(self, pattern_id: str, reason: str = "low_score"):
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE vote_records
            SET is_dormant = 1, dormancy_reason = ?
            WHERE pattern_id = ?
        """, (reason, pattern_id))

        conn.commit()
        conn.close()

    def get_all_scores(self) -> Dict[str, float]:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT pattern_id, avg_score FROM vote_records")
        rows = cursor.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}

    def get_stats(self) -> Dict[str, Any]:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM vote_records")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(avg_score) FROM vote_records")
        avg = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM vote_records WHERE is_dormant = 1")
        dormant = cursor.fetchone()[0]

        conn.close()

        return {
            "total_patterns": total,
            "avg_score": round(avg, 4),
            "dormant_count": dormant,
            "active_count": total - dormant,
        }
