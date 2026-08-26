# -*- coding: utf-8 -*-
"""
数据加载公共工具（缓存等）
（2026-08-26 小二陈：从 core/data_loader.py 拆出，接口不变）
"""
from core.logger import get_logger

logger = get_logger(__name__)

import pandas as pd
from pathlib import Path

_STOCKDB_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache" / "stockdb"

def _cache_path(symbol: str, frequency: str):
    freq_tag = "1d" if frequency in (None, "1d", "1D") else str(frequency)
    return _STOCKDB_CACHE_DIR / f"{symbol}_{freq_tag}.csv"

def _load_stockdb_cache(symbol: str, frequency: str):
    """读缓存，返回 date 索引的 DataFrame，无缓存/损坏返回 None"""
    p = _cache_path(symbol, frequency)
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p)
        if 'date' not in df.columns or df.empty:
            return None
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date']).set_index('date').sort_index()
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception:
        return None

def _save_stockdb_cache(symbol: str, frequency: str, df) -> None:
    """写缓存（覆盖合并后的全量结果）"""
    try:
        _STOCKDB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(_cache_path(symbol, frequency), encoding='utf-8')
    except Exception as e:
        logger.error(f"⚠️ 缓存写入失败 {symbol}: {e}")

