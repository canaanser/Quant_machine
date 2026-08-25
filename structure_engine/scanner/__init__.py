"""
扫描器模块
"""
from .wave_detector import detect_waves
from .pattern_scanner import scan_patterns
from .segment_extractor import extract_segments, Segment

__all__ = [
    'detect_waves',
    'scan_patterns',
    'extract_segments',
    'Segment',
]