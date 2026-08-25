"""
结构感知层 (Structure Engine)
提供形态识别、片段截取、索引存储与相似度匹配能力
"""
from .scanner.wave_detector import detect_waves
from .scanner.pattern_scanner import scan_patterns
from .scanner.segment_extractor import extract_segments
from .index_engine.index_store import IndexStore
from .index_engine.query_engine import query_similar
from .voting.vote_pool import VotePool

__all__ = [
    'detect_waves',
    'scan_patterns',
    'extract_segments',
    'IndexStore',
    'query_similar',
    'VotePool',
]