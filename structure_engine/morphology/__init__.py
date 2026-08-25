"""
形态生成框架
"""
from .registry import REGISTRY, MorphologyRegistry
from .atomic import (
    AtomicFeature,
    BodyRatio,
    ShadowRatio,
    GapDetector,
    EngulfingDetector,
    InsideDetector,
    ConsecutiveBars,
    VolumeSpike,
)

__all__ = [
    'REGISTRY',
    'MorphologyRegistry',
    'AtomicFeature',
    'BodyRatio',
    'ShadowRatio',
    'GapDetector',
    'EngulfingDetector',
    'InsideDetector',
    'ConsecutiveBars',
    'VolumeSpike',
]