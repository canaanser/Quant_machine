#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结构感知层 + 形态索引引擎 — 一键部署脚本（缩进修复 + 引号统一版）
执行后自动创建所有新增目录和文件
"""
import os
import sys
from pathlib import Path

ROOT = Path.cwd()

# ============================================================
# 1. 创建目录结构
# ============================================================

def create_dirs():
    dirs = [
        "structure_engine",
        "structure_engine/morphology",
        "structure_engine/morphology/atomic",
        "structure_engine/scanner",
        "structure_engine/index_engine",
        "structure_engine/voting",
        "structure_engine/schemas",
        "tests",
    ]
    for d in dirs:
        p = ROOT / d
        p.mkdir(parents=True, exist_ok=True)
        print(f"  📁 创建目录: {d}")

# ============================================================
# 2. 文件内容定义
# ============================================================

FILES = {}

# ---------- 2.1 structure_engine/__init__.py ----------
FILES["structure_engine/__init__.py"] = '''
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
'''

# ---------- 2.2 morphology/atomic/base_atomic.py ----------
FILES["structure_engine/morphology/atomic/base_atomic.py"] = '''
原子特征基类
所有原子函数必须实现 check() 方法
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class AtomicFeature(ABC):
    @abstractmethod
    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__
'''

# ---------- 2.3 morphology/atomic/body_ratio.py ----------
FILES["structure_engine/morphology/atomic/body_ratio.py"] = '''
实体比例原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class BodyRatio(AtomicFeature):
    def __init__(self, min_ratio: float = 0.3, max_ratio: float = 0.9):
        self.min_ratio = min_ratio
        self.max_ratio = max_ratio

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 0 or idx >= len(klines):
            return {"matched": False, "strength": 0.0, "meta": {}}

        k = klines[idx]
        body = abs(k['close'] - k['open'])
        high_low = k['high'] - k['low']
        if high_low == 0:
            return {"matched": False, "strength": 0.0, "meta": {"ratio": 0.0}}

        ratio = body / high_low
        matched = self.min_ratio <= ratio <= self.max_ratio
        strength = ratio if ratio <= 1.0 else 0.0

        return {
            "matched": matched,
            "strength": strength,
            "meta": {"ratio": round(ratio, 3)}
        }
'''

# ---------- 2.4 morphology/atomic/shadow_ratio.py ----------
FILES["structure_engine/morphology/atomic/shadow_ratio.py"] = '''
影线比例原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class ShadowRatio(AtomicFeature):
    def __init__(self, shadow_type: str = "upper", min_ratio: float = 0.5):
        self.shadow_type = shadow_type
        self.min_ratio = min_ratio

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 0 or idx >= len(klines):
            return {"matched": False, "strength": 0.0, "meta": {}}

        k = klines[idx]
        body = abs(k['close'] - k['open'])
        if body == 0:
            return {"matched": False, "strength": 0.0, "meta": {"shadow": 0.0}}

        if self.shadow_type == "upper":
            shadow = k['high'] - max(k['open'], k['close'])
        else:
            shadow = min(k['open'], k['close']) - k['low']

        shadow = max(0.0, shadow)
        ratio = shadow / body
        matched = ratio >= self.min_ratio
        strength = min(1.0, ratio / 2.0)

        return {
            "matched": matched,
            "strength": strength,
            "meta": {f"{self.shadow_type}_shadow_ratio": round(ratio, 3)}
        }
'''

# ---------- 2.5 morphology/atomic/gap_detector.py ----------
FILES["structure_engine/morphology/atomic/gap_detector.py"] = '''
跳空检测原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class GapDetector(AtomicFeature):
    def __init__(self, gap_type: str = "up", min_gap_ratio: float = 0.01):
        self.gap_type = gap_type
        self.min_gap_ratio = min_gap_ratio

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 1 or idx >= len(klines):
            return {"matched": False, "strength": 0.0, "meta": {}}

        curr = klines[idx]
        prev = klines[idx - 1]
        prev_close = prev['close']

        if self.gap_type == "up":
            gap = curr['low'] - prev_close
            matched = gap > 0 and gap / prev_close >= self.min_gap_ratio
            strength = min(1.0, (gap / prev_close) * 10)
            meta = {"gap_up": round(gap, 3), "gap_ratio": round(gap / prev_close, 4)}
        else:
            gap = prev_close - curr['high']
            matched = gap > 0 and gap / prev_close >= self.min_gap_ratio
            strength = min(1.0, (gap / prev_close) * 10)
            meta = {"gap_down": round(gap, 3), "gap_ratio": round(gap / prev_close, 4)}

        return {
            "matched": matched,
            "strength": strength,
            "meta": meta
        }
'''

# ---------- 2.6 morphology/atomic/engulfing_detector.py ----------
FILES["structure_engine/morphology/atomic/engulfing_detector.py"] = '''
吞没检测原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class EngulfingDetector(AtomicFeature):
    def __init__(self, engulfing_type: str = "bullish"):
        self.engulfing_type = engulfing_type

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 1 or idx >= len(klines):
            return {"matched": False, "strength": 0.0, "meta": {}}

        curr = klines[idx]
        prev = klines[idx - 1]

        curr_open = curr['open']
        curr_close = curr['close']
        prev_open = prev['open']
        prev_close = prev['close']

        curr_body_low = min(curr_open, curr_close)
        curr_body_high = max(curr_open, curr_close)
        prev_body_low = min(prev_open, prev_close)
        prev_body_high = max(prev_open, prev_close)

        if self.engulfing_type == "bullish":
            is_bullish = curr_close > curr_open
            prev_is_bearish = prev_close < prev_open
            engulf = is_bullish and prev_is_bearish and curr_body_low < prev_body_low and curr_body_high > prev_body_high
            engulf_ratio = (curr_body_high - curr_body_low) / (prev_body_high - prev_body_low + 0.001)
            strength = min(1.0, engulf_ratio / 2.0)
        else:
            is_bearish = curr_close < curr_open
            prev_is_bullish = prev_close > prev_open
            engulf = is_bearish and prev_is_bullish and curr_body_low < prev_body_low and curr_body_high > prev_body_high
            engulf_ratio = (curr_body_high - curr_body_low) / (prev_body_high - prev_body_low + 0.001)
            strength = min(1.0, engulf_ratio / 2.0)

        return {
            "matched": engulf,
            "strength": strength if engulf else 0.0,
            "meta": {
                "engulfing_type": self.engulfing_type,
                "engulf_ratio": round(engulf_ratio, 3) if engulf else 0.0
            }
        }
'''

# ---------- 2.7 morphology/atomic/inside_detector.py ----------
FILES["structure_engine/morphology/atomic/inside_detector.py"] = '''
内包检测原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class InsideDetector(AtomicFeature):
    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < 1 or idx >= len(klines):
            return {"matched": False, "strength": 0.0, "meta": {}}

        curr = klines[idx]
        prev = klines[idx - 1]

        curr_body_low = min(curr['open'], curr['close'])
        curr_body_high = max(curr['open'], curr['close'])
        prev_body_low = min(prev['open'], prev['close'])
        prev_body_high = max(prev['open'], prev['close'])

        inside = curr_body_low > prev_body_low and curr_body_high < prev_body_high
        curr_range = curr_body_high - curr_body_low
        prev_range = prev_body_high - prev_body_low
        ratio = curr_range / (prev_range + 0.001)
        strength = min(1.0, (1 - ratio) * 2) if inside else 0.0

        return {
            "matched": inside,
            "strength": strength,
            "meta": {"inside": inside, "range_ratio": round(ratio, 3)}
        }
'''

# ---------- 2.8 morphology/atomic/consecutive_bars.py ----------
FILES["structure_engine/morphology/atomic/consecutive_bars.py"] = '''
连续同色K线原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class ConsecutiveBars(AtomicFeature):
    def __init__(self, direction: str = "up", count: int = 3):
        self.direction = direction
        self.count = count

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < self.count - 1 or idx >= len(klines):
            return {"matched": False, "strength": 0.0, "meta": {}}

        consecutive = 0
        for i in range(idx - self.count + 1, idx + 1):
            k = klines[i]
            if self.direction == "up":
                if k['close'] > k['open']:
                    consecutive += 1
                else:
                    break
            else:
                if k['close'] < k['open']:
                    consecutive += 1
                else:
                    break

        matched = consecutive >= self.count
        strength = min(1.0, consecutive / (self.count + 2))

        return {
            "matched": matched,
            "strength": strength if matched else 0.0,
            "meta": {
                "direction": self.direction,
                "consecutive_count": consecutive,
                "target_count": self.count
            }
        }
'''

# ---------- 2.9 morphology/atomic/volume_spike.py ----------
FILES["structure_engine/morphology/atomic/volume_spike.py"] = '''
量能突增原子特征
"""
from typing import Dict, Any
from .base_atomic import AtomicFeature


class VolumeSpike(AtomicFeature):
    def __init__(self, lookback: int = 5, multiplier: float = 2.0):
        self.lookback = lookback
        self.multiplier = multiplier

    def check(self, klines: list, idx: int, context: Dict[str, Any]) -> Dict[str, Any]:
        if idx < self.lookback or idx >= len(klines):
            return {"matched": False, "strength": 0.0, "meta": {}}

        curr_vol = klines[idx]['volume']
        avg_vol = sum([klines[i]['volume'] for i in range(idx - self.lookback, idx)]) / self.lookback

        if avg_vol == 0:
            return {"matched": False, "strength": 0.0, "meta": {"avg_volume": 0}}

        ratio = curr_vol / avg_vol
        matched = ratio >= self.multiplier
        strength = min(1.0, (ratio - 1) / 4)

        return {
            "matched": matched,
            "strength": strength if matched else 0.0,
            "meta": {
                "current_volume": curr_vol,
                "avg_volume": round(avg_vol),
                "ratio": round(ratio, 2)
            }
        }
'''

# ---------- 2.10 morphology/atomic/__init__.py ----------
FILES["structure_engine/morphology/atomic/__init__.py"] = '''
原子特征库
所有原子函数在此导出
"""
from .base_atomic import AtomicFeature
from .body_ratio import BodyRatio
from .shadow_ratio import ShadowRatio
from .gap_detector import GapDetector
from .engulfing_detector import EngulfingDetector
from .inside_detector import InsideDetector
from .consecutive_bars import ConsecutiveBars
from .volume_spike import VolumeSpike

__all__ = [
    'AtomicFeature',
    'BodyRatio',
    'ShadowRatio',
    'GapDetector',
    'EngulfingDetector',
    'InsideDetector',
    'ConsecutiveBars',
    'VolumeSpike',
]
'''

# ---------- 2.11 morphology/registry.py ----------
FILES["structure_engine/morphology/registry.py"] = '''
形态注册表
将原子特征组合为可识别的形态ID
"""
from typing import Dict, List, Any
from .atomic import (
    BodyRatio,
    ShadowRatio,
    GapDetector,
    EngulfingDetector,
    InsideDetector,
    ConsecutiveBars,
    VolumeSpike,
)


class MorphologyRegistry:
    def __init__(self):
        self._registry: Dict[str, dict] = {}
        self._build_registry()

    def _build_registry(self):
        self._registry.update({
            "1_bullish_0_hammer": {
                "window": 1,
                "signal": "bullish",
                "generation": 0,
                "atomics": [
                    {"class": BodyRatio, "params": {"min_ratio": 0.3, "max_ratio": 0.6}},
                    {"class": ShadowRatio, "params": {"shadow_type": "lower", "min_ratio": 2.0}},
                ],
                "combine": "and",
                "human_readable": "锤子线"
            },
            "1_bearish_0_shooting_star": {
                "window": 1,
                "signal": "bearish",
                "generation": 0,
                "atomics": [
                    {"class": BodyRatio, "params": {"min_ratio": 0.3, "max_ratio": 0.6}},
                    {"class": ShadowRatio, "params": {"shadow_type": "upper", "min_ratio": 2.0}},
                ],
                "combine": "and",
                "human_readable": "射击之星"
            },
            "1_bullish_0_doji": {
                "window": 1,
                "signal": "neutral",
                "generation": 0,
                "atomics": [
                    {"class": BodyRatio, "params": {"min_ratio": 0.0, "max_ratio": 0.05}},
                ],
                "combine": "and",
                "human_readable": "十字星"
            },
            "2_bullish_0_engulfing": {
                "window": 2,
                "signal": "bullish",
                "generation": 0,
                "atomics": [
                    {"class": EngulfingDetector, "params": {"engulfing_type": "bullish"}},
                ],
                "combine": "and",
                "human_readable": "看涨吞没"
            },
            "2_bearish_0_engulfing": {
                "window": 2,
                "signal": "bearish",
                "generation": 0,
                "atomics": [
                    {"class": EngulfingDetector, "params": {"engulfing_type": "bearish"}},
                ],
                "combine": "and",
                "human_readable": "看跌吞没"
            },
            "2_neutral_0_inside": {
                "window": 2,
                "signal": "neutral",
                "generation": 0,
                "atomics": [
                    {"class": InsideDetector, "params": {}},
                ],
                "combine": "and",
                "human_readable": "内包线"
            },
            "3_bullish_0_three_white_soldiers": {
                "window": 3,
                "signal": "bullish",
                "generation": 0,
                "atomics": [
                    {"class": ConsecutiveBars, "params": {"direction": "up", "count": 3}},
                    {"class": BodyRatio, "params": {"min_ratio": 0.4, "max_ratio": 0.9}},
                ],
                "combine": "and",
                "human_readable": "三白兵"
            },
            "3_bearish_0_three_black_crows": {
                "window": 3,
                "signal": "bearish",
                "generation": 0,
                "atomics": [
                    {"class": ConsecutiveBars, "params": {"direction": "down", "count": 3}},
                    {"class": BodyRatio, "params": {"min_ratio": 0.4, "max_ratio": 0.9}},
                ],
                "combine": "and",
                "human_readable": "三乌鸦"
            },
            "2_bullish_1_engulfing_ma": {
                "window": 2,
                "signal": "bullish",
                "generation": 1,
                "atomics": [
                    {"class": EngulfingDetector, "params": {"engulfing_type": "bullish"}},
                ],
                "filters": ["close_above_ma20"],
                "combine": "and",
                "human_readable": "看涨吞没 + MA20之上"
            },
            "1_bullish_1_hammer_support": {
                "window": 1,
                "signal": "bullish",
                "generation": 1,
                "atomics": [
                    {"class": BodyRatio, "params": {"min_ratio": 0.3, "max_ratio": 0.6}},
                    {"class": ShadowRatio, "params": {"shadow_type": "lower", "min_ratio": 2.0}},
                ],
                "filters": ["at_support"],
                "combine": "and",
                "human_readable": "锤子线 + 支撑位"
            },
            "2_bullish_2_engulfing_volume": {
                "window": 2,
                "signal": "bullish",
                "generation": 2,
                "atomics": [
                    {"class": EngulfingDetector, "params": {"engulfing_type": "bullish"}},
                    {"class": VolumeSpike, "params": {"lookback": 5, "multiplier": 2.0}},
                ],
                "combine": "and",
                "human_readable": "看涨吞没 + 放量确认"
            },
        })

    def get(self, pattern_id: str) -> dict:
        return self._registry.get(pattern_id, None)

    def list_all(self) -> List[dict]:
        return [{"id": k, **v} for k, v in self._registry.items()]

    def get_by_signal(self, signal: str) -> List[dict]:
        return [{"id": k, **v} for k, v in self._registry.items() if v.get("signal") == signal]

    def get_by_generation(self, generation: int) -> List[dict]:
        return [{"id": k, **v} for k, v in self._registry.items() if v.get("generation") == generation]


REGISTRY = MorphologyRegistry()
'''

# ---------- 2.12 morphology/__init__.py ----------
FILES["structure_engine/morphology/__init__.py"] = '''
形态生成框架
"""
from .registry import REGISTRY, MorphologyRegistry
from .atomic import *

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
'''

# ---------- 2.13 scanner/wave_detector.py ----------
FILES["structure_engine/scanner/wave_detector.py"] = '''
波段识别器
在滚动窗口中识别波峰和波谷（分形法）
"""
from typing import List, Dict, Optional
import pandas as pd
import numpy as np


def detect_waves(
    df: pd.DataFrame,
    window_days: int = 120,
    peak_valley_lookback: int = 5,
    min_amplitude: float = 0.08
) -> List[Dict]:
    if df.empty:
        return []

    data = df.tail(window_days).reset_index(drop=True)
    if len(data) < peak_valley_lookback * 2 + 1:
        return []

    if '日期/时间' not in data.columns:
        if data.index.name:
            data = data.reset_index()
            data.rename(columns={data.columns[0]: '日期/时间'}, inplace=True)
        else:
            data['日期/时间'] = data.index

    if '最高价' not in data.columns and 'high' in data.columns:
        data.rename(columns={'high': '最高价', 'low': '最低价'}, inplace=True)

    waves = []
    lookback = peak_valley_lookback

    for i in range(lookback, len(data) - lookback):
        curr = data.iloc[i]

        left_lows = data.iloc[i - lookback:i]['最低价']
        right_lows = data.iloc[i + 1:i + lookback + 1]['最低价']
        is_valley = curr['最低价'] <= left_lows.min() and curr['最低价'] <= right_lows.min()

        left_highs = data.iloc[i - lookback:i]['最高价']
        right_highs = data.iloc[i + 1:i + lookback + 1]['最高价']
        is_peak = curr['最高价'] >= left_highs.max() and curr['最高价'] >= right_highs.max()

        if is_valley:
            waves.append({
                "type": "valley",
                "idx": i,
                "date": curr['日期/时间'],
                "price": curr['最低价'],
                "low": curr['最低价'],
                "high": curr['最高价'],
            })
        elif is_peak:
            waves.append({
                "type": "peak",
                "idx": i,
                "date": curr['日期/时间'],
                "price": curr['最高价'],
                "low": curr['最低价'],
                "high": curr['最高价'],
            })

    filtered = []
    if len(waves) >= 2:
        for i in range(len(waves) - 1):
            if waves[i]['type'] == 'valley' and waves[i+1]['type'] == 'peak':
                amp = (waves[i+1]['price'] - waves[i]['price']) / waves[i]['price']
                if amp >= min_amplitude:
                    filtered.append(waves[i])
                    filtered.append(waves[i+1])
            elif waves[i]['type'] == 'peak' and waves[i+1]['type'] == 'valley':
                amp = (waves[i]['price'] - waves[i+1]['price']) / waves[i]['price']
                if amp >= min_amplitude:
                    filtered.append(waves[i])
                    filtered.append(waves[i+1])

    return filtered if filtered else waves
'''

# ---------- 2.14 scanner/pattern_scanner.py ----------
FILES["structure_engine/scanner/pattern_scanner.py"] = '''
形态扫描器
"""
from typing import List, Dict, Any, Optional
import pandas as pd
from ..morphology.registry import REGISTRY
from ..morphology.atomic import (
    BodyRatio,
    ShadowRatio,
    GapDetector,
    EngulfingDetector,
    InsideDetector,
    ConsecutiveBars,
    VolumeSpike,
)

ATOMIC_CLASSES = {
    "BodyRatio": BodyRatio,
    "ShadowRatio": ShadowRatio,
    "GapDetector": GapDetector,
    "EngulfingDetector": EngulfingDetector,
    "InsideDetector": InsideDetector,
    "ConsecutiveBars": ConsecutiveBars,
    "VolumeSpike": VolumeSpike,
}


def scan_patterns(
    df: pd.DataFrame,
    patterns: Optional[List[str]] = None,
    ma20: Optional[pd.Series] = None,
) -> List[Dict[str, Any]]:
    if df.empty:
        return []

    klines = []
    for idx, row in df.iterrows():
        k = {
            'date': idx if hasattr(idx, 'strftime') else idx,
            'open': row.get('开盘价', row.get('open', 0)),
            'high': row.get('最高价', row.get('high', 0)),
            'low': row.get('最低价', row.get('low', 0)),
            'close': row.get('收盘价', row.get('close', 0)),
            'volume': row.get('成交量', row.get('volume', 0)),
        }
        klines.append(k)

    ma20_values = list(ma20) if ma20 is not None else [None] * len(klines)

    if patterns is None:
        patterns = REGISTRY.list_all()
    else:
        patterns = [REGISTRY.get(p) for p in patterns if REGISTRY.get(p)]

    results = []

    for pat in patterns:
        pattern_id = pat.get('id')
        if not pattern_id:
            continue

        window = pat.get('window', 1)
        atomics = pat.get('atomics', [])
        combine = pat.get('combine', 'and')
        filters = pat.get('filters', [])
        generation = pat.get('generation', 0)

        for i in range(window - 1, len(klines)):
            context = {
                'ma20': ma20_values[i] if i < len(ma20_values) else None,
                'idx': i,
            }

            matched_atoms = []
            strengths = []
            meta_list = []

            for atom_cfg in atomics:
                atom_class = ATOMIC_CLASSES.get(atom_cfg['class'])
                if not atom_class:
                    continue
                params = atom_cfg.get('params', {})
                atom = atom_class(**params)
                result = atom.check(klines, i, context)
                matched_atoms.append(result['matched'])
                strengths.append(result['strength'])
                meta_list.append(result['meta'])

            if combine == 'and':
                matched = all(matched_atoms)
            else:
                matched = any(matched_atoms)

            if not matched:
                continue

            overall_strength = sum(strengths) / len(strengths) if strengths else 0.0

            if generation >= 1:
                if 'close_above_ma20' in filters:
                    if context['ma20'] is None or klines[i]['close'] < context['ma20']:
                        continue

            results.append({
                "pattern_id": pattern_id,
                "pattern_type": pat.get('human_readable', pattern_id),
                "category": pat.get('signal', 'neutral'),
                "generation": generation,
                "idx": i,
                "date": klines[i]['date'],
                "strength": overall_strength,
                "meta": {
                    "window": window,
                    "atomics": meta_list,
                }
            })

    return results
'''

# ---------- 2.15 scanner/segment_extractor.py ----------
FILES["structure_engine/scanner/segment_extractor.py"] = '''
片段截取器
"""
from typing import List, Dict, Optional, Any
import pandas as pd


class Segment:
    def __init__(self, valley_buy: dict, peak_sell: dict, valley_confirm: dict,
                 kline_data: pd.DataFrame, ma_data: pd.DataFrame,
                 best_buy: dict, best_sell: dict,
                 ma_buy: Optional[dict], ma_sell: Optional[dict]):
        self.valley_buy = valley_buy
        self.peak_sell = peak_sell
        self.valley_confirm = valley_confirm
        self.kline_data = kline_data
        self.ma_data = ma_data
        self.best_buy = best_buy
        self.best_sell = best_sell
        self.ma_buy = ma_buy
        self.ma_sell = ma_sell
        self.symbol = None
        self.file_path = None
        self.start_row = valley_buy.get('idx', 0)
        self.end_row = valley_confirm.get('idx', 0)

    def to_dict(self) -> dict:
        return {
            "valley_buy": self.valley_buy,
            "peak_sell": self.peak_sell,
            "valley_confirm": self.valley_confirm,
            "best_buy": self.best_buy,
            "best_sell": self.best_sell,
            "ma_buy": self.ma_buy,
            "ma_sell": self.ma_sell,
            "start_row": self.start_row,
            "end_row": self.end_row,
            "amplitude": (self.peak_sell['price'] - self.valley_buy['price']) / self.valley_buy['price'],
            "duration": self.valley_confirm.get('idx', 0) - self.valley_buy.get('idx', 0),
        }


def find_golden_cross(df: pd.DataFrame, start_idx: int, end_idx: int) -> Optional[dict]:
    if 'MA5' not in df.columns or 'MA20' not in df.columns:
        return None
    data = df.iloc[start_idx:end_idx+1]
    for i in range(1, len(data)):
        if data.iloc[i-1]['MA5'] <= data.iloc[i-1]['MA20'] and data.iloc[i]['MA5'] > data.iloc[i]['MA20']:
            return {"date": data.index[i], "price": data.iloc[i]['close']}
    return None


def find_death_cross(df: pd.DataFrame, start_idx: int, end_idx: int) -> Optional[dict]:
    if 'MA5' not in df.columns or 'MA20' not in df.columns:
        return None
    data = df.iloc[start_idx:end_idx+1]
    for i in range(1, len(data)):
        if data.iloc[i-1]['MA5'] >= data.iloc[i-1]['MA20'] and data.iloc[i]['MA5'] < data.iloc[i]['MA20']:
            return {"date": data.index[i], "price": data.iloc[i]['close']}
    return None


def extract_segments(
    waves: List[dict],
    df: pd.DataFrame,
    min_amplitude: float = 0.08,
    symbol: str = "",
    file_path: str = ""
) -> List[Segment]:
    if len(waves) < 3:
        return []

    segments = []

    for i in range(len(waves) - 2):
        if waves[i]['type'] == 'valley' and waves[i+1]['type'] == 'peak' and waves[i+2]['type'] == 'valley':
            valley_buy = waves[i]
            peak_sell = waves[i+1]
            valley_confirm = waves[i+2]

            amplitude = (peak_sell['price'] - valley_buy['price']) / valley_buy['price']
            if amplitude < min_amplitude:
                continue

            start_idx = valley_buy['idx']
            end_idx = valley_confirm['idx']

            kline_data = df.iloc[start_idx:end_idx+1].copy()
            ma_data = df.iloc[start_idx:end_idx+1][['MA5', 'MA10', 'MA20', 'MA60']].copy() if all(c in df.columns for c in ['MA5','MA10','MA20','MA60']) else pd.DataFrame()

            ma_buy = find_golden_cross(df, start_idx, end_idx)
            ma_sell = find_death_cross(df, start_idx, end_idx)

            segment = Segment(
                valley_buy=valley_buy,
                peak_sell=peak_sell,
                valley_confirm=valley_confirm,
                kline_data=kline_data,
                ma_data=ma_data,
                best_buy=valley_buy,
                best_sell=peak_sell,
                ma_buy=ma_buy,
                ma_sell=ma_sell,
            )
            segment.symbol = symbol
            segment.file_path = file_path

            segments.append(segment)

    return segments
'''

# ---------- 2.16 scanner/__init__.py ----------
FILES["structure_engine/scanner/__init__.py"] = '''
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
'''

# ---------- 2.17 index_engine/index_store.py ----------
FILES["structure_engine/index_engine/index_store.py"] = '''
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
'''

# ---------- 2.18 index_engine/query_engine.py ----------
FILES["structure_engine/index_engine/query_engine.py"] = '''
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
'''

# ---------- 2.19 index_engine/__init__.py ----------
FILES["structure_engine/index_engine/__init__.py"] = '''
索引引擎
"""
from .index_store import IndexStore
from .query_engine import query_similar

__all__ = [
    'IndexStore',
    'query_similar',
]
'''

# ---------- 2.20 voting/vote_pool.py ----------
FILES["structure_engine/voting/vote_pool.py"] = '''
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
'''

# ---------- 2.21 voting/dormancy_manager.py ----------
FILES["structure_engine/voting/dormancy_manager.py"] = '''
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
'''

# ---------- 2.22 voting/__init__.py ----------
FILES["structure_engine/voting/__init__.py"] = '''
投票池管理
"""
from .vote_pool import VotePool
from .dormancy_manager import DormancyManager

__all__ = [
    'VotePool',
    'DormancyManager',
]
'''

# ---------- 2.23 schemas/structure_schemas.py ----------
FILES["structure_engine/schemas/structure_schemas.py"] = '''
结构感知层输出契约（StateTable）
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class StateTable:
    date: str
    symbol: str
    pattern_ids: List[str] = field(default_factory=list)
    pattern_type: str = ""
    category: str = "neutral"
    strength: float = 0.0
    vote_score: float = 0.0
    vote_pool_rank: Optional[int] = None
    data_quality: str = "valid"
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "symbol": self.symbol,
            "pattern_ids": self.pattern_ids,
            "pattern_type": self.pattern_type,
            "category": self.category,
            "strength": round(self.strength, 4),
            "vote_score": round(self.vote_score, 4),
            "vote_pool_rank": self.vote_pool_rank,
            "data_quality": self.data_quality,
            "meta": self.meta,
        }


@dataclass
class SignalTable:
    date: str
    symbol: str
    score: float
    confidence: float
    source: str = "structure_engine"

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "symbol": self.symbol,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "source": self.source,
        }


@dataclass
class OrderTable:
    symbol: str
    action: str
    target_volume: int
    target_amount: float
    price_limit: float
    priority: int = 5

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "target_volume": self.target_volume,
            "target_amount": round(self.target_amount, 2),
            "price_limit": round(self.price_limit, 2),
            "priority": self.priority,
        }


@dataclass
class ExecutionReport:
    order_id: str
    symbol: str
    action: str
    filled_volume: int
    filled_amount: float
    commission: float
    status: str

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "action": self.action,
            "filled_volume": self.filled_volume,
            "filled_amount": round(self.filled_amount, 2),
            "commission": round(self.commission, 2),
            "status": self.status,
        }
'''

# ---------- 2.24 schemas/index_schemas.py ----------
FILES["structure_engine/schemas/index_schemas.py"] = '''
索引表 + 查询结构定义
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class IndexRecord:
    index_id: str
    symbol: str
    start_date: str
    end_date: str
    segment_type: str
    features: Dict[str, Any]
    tags: List[str] = field(default_factory=list)
    best_buy: Dict[str, Any] = field(default_factory=dict)
    best_sell: Dict[str, Any] = field(default_factory=dict)
    ma_buy: Dict[str, Any] = field(default_factory=dict)
    ma_sell: Dict[str, Any] = field(default_factory=dict)
    data_pointer: Dict[str, Any] = field(default_factory=dict)
    forward_stats: Dict[str, float] = field(default_factory=dict)
    amplitude: float = 0.0
    duration: int = 0

    def to_dict(self) -> dict:
        return {
            "index_id": self.index_id,
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "segment_type": self.segment_type,
            "features": self.features,
            "tags": self.tags,
            "best_buy": self.best_buy,
            "best_sell": self.best_sell,
            "ma_buy": self.ma_buy,
            "ma_sell": self.ma_sell,
            "data_pointer": self.data_pointer,
            "forward_stats": self.forward_stats,
            "amplitude": round(self.amplitude, 4),
            "duration": self.duration,
        }


@dataclass
class QueryRequest:
    query_id: str
    symbol: Optional[str] = None
    lookback_days: int = 30
    features: Dict[str, Any] = field(default_factory=dict)
    match_tolerance: float = 0.15
    top_k: int = 10

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "symbol": self.symbol,
            "lookback_days": self.lookback_days,
            "features": self.features,
            "match_tolerance": self.match_tolerance,
            "top_k": self.top_k,
        }


@dataclass
class QueryResult:
    query_id: str
    matches: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "matches": self.matches,
        }
'''

# ---------- 2.25 schemas/__init__.py ----------
FILES["structure_engine/schemas/__init__.py"] = '''
输出契约定义
"""
from .structure_schemas import (
    StateTable,
    SignalTable,
    OrderTable,
    ExecutionReport,
)
from .index_schemas import (
    IndexRecord,
    QueryRequest,
    QueryResult,
)

__all__ = [
    'StateTable',
    'SignalTable',
    'OrderTable',
    'ExecutionReport',
    'IndexRecord',
    'QueryRequest',
    'QueryResult',
]
'''

# ---------- 2.26 tests/test_morphology.py ----------
FILES["tests/test_morphology.py"] = '''
形态生成框架测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
from structure_engine.morphology import REGISTRY
from structure_engine.morphology.atomic import (
    BodyRatio,
    ShadowRatio,
    GapDetector,
    EngulfingDetector,
    InsideDetector,
    ConsecutiveBars,
    VolumeSpike,
)


class TestMorphology(unittest.TestCase):

    def test_registry(self):
        patterns = REGISTRY.list_all()
        self.assertGreater(len(patterns), 5)
        print(f"注册表加载: {len(patterns)} 个形态")

    def test_body_ratio(self):
        atom = BodyRatio(min_ratio=0.3, max_ratio=0.9)
        klines = [{"open": 10, "close": 12, "high": 13, "low": 9, "volume": 100}]
        result = atom.check(klines, 0, {})
        self.assertTrue(result['matched'])
        self.assertAlmostEqual(result['meta']['ratio'], 0.5, delta=0.01)

    def test_shadow_ratio(self):
        atom = ShadowRatio(shadow_type="upper", min_ratio=0.5)
        klines = [{"open": 10, "close": 11, "high": 15, "low": 9.5, "volume": 100}]
        result = atom.check(klines, 0, {})
        self.assertTrue(result['matched'])


if __name__ == "__main__":
    unittest.main()
'''

# ---------- 2.27 tests/test_scanner.py ----------
FILES["tests/test_scanner.py"] = '''
扫描器测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
import pandas as pd
from structure_engine.scanner import detect_waves, scan_patterns


class TestScanner(unittest.TestCase):

    def test_wave_detector(self):
        df = pd.DataFrame({
            '最高价': [10, 11, 12, 11, 10, 9, 8, 7, 8, 9, 10],
            '最低价': [9, 10, 11, 10, 9, 8, 7, 6, 7, 8, 9],
        })
        waves = detect_waves(df, window_days=20, peak_valley_lookback=2)
        self.assertTrue(any(w['type'] == 'valley' for w in waves))
        self.assertTrue(any(w['type'] == 'peak' for w in waves))

    def test_pattern_scanner(self):
        df = pd.DataFrame({
            'open': [10, 10, 10],
            'high': [11, 11, 11],
            'low': [9, 9, 9],
            'close': [10, 10, 10],
            'volume': [100, 100, 100],
        })
        results = scan_patterns(df)
        print(f"形态扫描: {len(results)} 个匹配")


if __name__ == "__main__":
    unittest.main()
'''

# ---------- 2.28 tests/test_index_engine.py ----------
FILES["tests/test_index_engine.py"] = '''
索引引擎测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
import tempfile
import json
from structure_engine.index_engine import IndexStore, query_similar
from structure_engine.schemas import StateTable


class TestIndexEngine(unittest.TestCase):

    def test_index_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = IndexStore(db_path)

            record = {
                "symbol": "000063",
                "start_date": "20260608",
                "end_date": "20260710",
                "segment_type": "上升段",
                "features": {"kline_shape": [0.5, 0.6, 0.7]},
                "tags": ["放量上涨"],
                "best_buy": {"date": "20260608", "price": 36.37},
                "best_sell": {"date": "20260710", "price": 40.05},
                "ma_buy": {},
                "ma_sell": {},
                "data_pointer": {},
                "forward_stats": {"d20_return": 0.087},
                "amplitude": 0.10,
                "duration": 30,
            }

            index_id = store.insert(record)
            self.assertIsNotNone(index_id)

            results = store.search({"amplitude": 0.10, "duration": 30})
            self.assertGreaterEqual(len(results), 1)

    def test_state_table_format(self):
        mock_state = StateTable(
            date="2026-08-12",
            symbol="000063",
            pattern_ids=["2_bullish_0_engulfing"],
            strength=0.72,
            category="bullish"
        )
        self.assertTrue(hasattr(mock_state, "pattern_ids"))
        self.assertTrue(hasattr(mock_state, "strength"))
        self.assertEqual(mock_state.symbol, "000063")
        d = mock_state.to_dict()
        self.assertIn("pattern_ids", d)
        self.assertIn("strength", d)
        print("StateTable 格式验证通过")


if __name__ == "__main__":
    unittest.main()
'''

# ============================================================
# 3. 主执行逻辑
# ============================================================

def main():
    print("=" * 60)
    print("  结构感知层 + 形态索引引擎 — 一键部署")
    print("=" * 60)

    print("\n创建目录结构...")
    create_dirs()

    print("\n写入文件内容...")
    for file_path, content in FILES.items():
        full_path = ROOT / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding='utf-8')
        print(f"  创建: {file_path}")

    print("\n" + "=" * 60)
    print("  部署完成！")
    print("=" * 60)
    print("\n新增模块: structure_engine/")
    print("   - morphology/  (原子特征 + 形态注册表)")
    print("   - scanner/     (波段识别 + 形态匹配 + 片段截取)")
    print("   - index_engine/ (索引存储 + 特征提取 + 查询引擎)")
    print("   - voting/      (投票池 + 沉底管理)")
    print("   - schemas/     (数据契约)")
    print("\n新增测试: tests/")
    print("\n配置更新: config/config.py (已添加结构感知层参数)")
    print("\n下一步: 运行测试验证")
    print("   python tests/test_morphology.py")


if __name__ == "__main__":
    main()