
"""
查询引擎
基于特征值进行相似度匹配
"""
import uuid
from typing import Dict, Any, List, Optional
import numpy as np
from .index_store import IndexStore


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if len(a) != len(b):
        return 0.0
    a_norm = np.linalg.norm(a)
    b_norm = np.linalg.norm(b)
    if a_norm == 0 or b_norm == 0:
        return 0.0
    return float(np.dot(a, b) / (a_norm * b_norm))


def query_similar(
    features: Dict[str, Any],
    tolerance: float = 0.15,
    top_k: int = 10,
    symbol: Optional[str] = None,
    segment_type: Optional[str] = None,
) -> Dict[str, Any]:
    store = IndexStore()
    query_id = f"QRY_{uuid.uuid4().hex[:8]}"

    results = store.search(features, tolerance=tolerance)

    if not results:
        return {"query_id": query_id, "matches": []}

    if symbol:
        results = [r for r in results if r['symbol'] == symbol]
    if segment_type:
        results = [r for r in results if r['segment_type'] == segment_type]

    if not results:
        return {"query_id": query_id, "matches": []}

    target_shape = features.get('kline_shape', [])
    target_ma = features.get('ma_position', [])

    scored = []
    for r in results:
        r_shape = r.get('features', {}).get('kline_shape', [])
        r_ma = r.get('features', {}).get('ma_position', [])

        shape_sim = cosine_similarity(target_shape, r_shape) if target_shape and r_shape else 0.5
        ma_sim = cosine_similarity(target_ma, r_ma) if target_ma and r_ma else 0.5

        overall_sim = shape_sim * 0.7 + ma_sim * 0.3
        scored.append({"record": r, "similarity": overall_sim})

    scored.sort(key=lambda x: x['similarity'], reverse=True)

    matches = []
    for item in scored[:top_k]:
        r = item['record']
        matches.append({
            "index_id": r['index_id'],
            "similarity": round(item['similarity'], 4),
            "segment_type": r['segment_type'],
            "best_buy": r['best_buy'],
            "best_sell": r['best_sell'],
            "ma_buy": r['ma_buy'],
            "ma_sell": r['ma_sell'],
            "forward_stats": r['forward_stats'],
            "symbol": r['symbol'],
            "start_date": r['start_date'],
            "end_date": r['end_date'],
        })

    return {"query_id": query_id, "matches": matches}
