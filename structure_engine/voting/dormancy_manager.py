"""
动态沉底机制
"""
from typing import List, Dict, Any
from .vote_pool import VotePool


class DormancyManager:
    def __init__(self, threshold_multiplier: float = 0.3, min_occurrences: int = 5, check_interval_days: int = 7):
        self.threshold_multiplier = threshold_multiplier
        self.min_occurrences = min_occurrences
        self.check_interval_days = check_interval_days
        self.vote_pool = VotePool()

    def check_and_update(self) -> List[str]:
        all_scores = self.vote_pool.get_all_scores()
        if not all_scores:
            return []

        scores = list(all_scores.values())
        median_score = sorted(scores)[len(scores) // 2] if scores else 0.5
        threshold = median_score * self.threshold_multiplier

        dormant_list = []
        for pattern_id, avg_score in all_scores.items():
            conn = self.vote_pool._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT occurrence_count FROM vote_records WHERE pattern_id = ?", (pattern_id,))
            row = cursor.fetchone()
            conn.close()
            count = row[0] if row else 0

            if count < self.min_occurrences and avg_score < threshold:
                self.vote_pool.set_dormant(pattern_id, f"low_score({avg_score:.3f}) < threshold({threshold:.3f})")
                dormant_list.append(pattern_id)

        return dormant_list

    def get_active_patterns(self) -> List[str]:
        conn = self.vote_pool._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT pattern_id FROM vote_records WHERE is_dormant = 0")
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]

    def get_dormant_patterns(self) -> List[Dict[str, Any]]:
        conn = self.vote_pool._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT pattern_id, dormancy_reason FROM vote_records WHERE is_dormant = 1")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
