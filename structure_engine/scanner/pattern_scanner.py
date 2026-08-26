"""
形态扫描器 - 支持历史收益统计 + 数据写入 + 波段关联 + 位置映射 + pending 状态
兼容现有调用方（backtest.py 等），输出格式不变
"""

from core.logger import get_logger

logger = get_logger(__name__)

from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime
from structure_engine.morphology.registry import REGISTRY
from structure_engine.morphology.atomic import (
    BodyRatio,
    ShadowRatio,
    GapDetector,
    EngulfingDetector,
    InsideDetector,
    ConsecutiveBars,
    VolumeSpike,
    DirectionalBody,
    HammerDetector,
    PiercingDetector,
    StarDetector,
    ThreeMethodsDetector,
    ShadowBodyDetector,
)

from .score_calculator import signed_log_score, calc_base_score, calc_composite_return
from .data_writer import write_pattern_history, write_atomic_features

ATOMIC_CLASSES = {
    "BodyRatio": BodyRatio,
    "ShadowRatio": ShadowRatio,
    "GapDetector": GapDetector,
    "EngulfingDetector": EngulfingDetector,
    "InsideDetector": InsideDetector,
    "ConsecutiveBars": ConsecutiveBars,
    "VolumeSpike": VolumeSpike,
    "DirectionalBody": DirectionalBody,
    "HammerDetector": HammerDetector,
    "PiercingDetector": PiercingDetector,
    "StarDetector": StarDetector,
    "ThreeMethodsDetector": ThreeMethodsDetector,
    "ShadowBodyDetector": ShadowBodyDetector,
}


def _calc_return(klines: List[dict], idx: int, days: int) -> float:
    """
    计算从 idx 日期开始，往后 days 个交易日的收益率
    如果数据不足，返回 0.0
    """
    if idx + days >= len(klines):
        return 0.0
    start_price = klines[idx]['close']
    end_price = klines[idx + days]['close']
    if start_price == 0:
        return 0.0
    return (end_price - start_price) / start_price


def scan_patterns(
    df: pd.DataFrame,
    patterns: Optional[List[str]] = None,
    ma20: Optional[pd.Series] = None,
    debug: bool = False,
    write_to_db: bool = True,
    symbol: str = "UNKNOWN",
    peak_date: Optional[str] = None,
    valley_date: Optional[str] = None,
    band_position: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    扫描历史数据，匹配形态并计算收益率。
    输出格式与现有版本完全一致，保证调用方不受影响。

    参数：
        df: OHLCV 数据
        patterns: 指定扫描的形态ID列表，None表示全部
        ma20: 预留参数
        debug: 是否打印调试日志
        write_to_db: 是否写入数据库（默认 True）
        symbol: 股票代码（写入数据库需要）
        peak_date: 所属波段的波峰日期（可选）
        valley_date: 所属波段的波谷日期（可选）
        band_position: 形态在波段中的位置标签（可选）

    返回：
        匹配到的形态列表，格式与现有版本一致
    """
    if df.empty:
        return []

    # 构建K线列表
    klines = []
    for idx, row in df.iterrows():
        klines.append({
            'date': idx if hasattr(idx, 'strftime') else idx,
            'open': row.get('open', row.get('开盘价', 0)),
            'high': row.get('high', row.get('最高价', 0)),
            'low': row.get('low', row.get('最低价', 0)),
            'close': row.get('close', row.get('收盘价', 0)),
            'volume': row.get('volume', row.get('成交量', 0)),
        })

    if debug:
        logger.debug(f"   📊 K线数量: {len(klines)}")

    if patterns is None:
        patterns = REGISTRY.list_all()
    else:
        patterns = [{"id": p, **REGISTRY.get(p)} for p in patterns if REGISTRY.get(p)]

    if debug:
        logger.debug(f"   📋 形态数量: {len(patterns)}")

    results = []

    for pat in patterns:
        pattern_id = pat.get('id')
        if not pattern_id:
            continue

        window = pat.get('window', 1)
        atomics = pat.get('atomics', [])
        threshold = pat.get('threshold', {})
        human_readable = pat.get('human_readable', pattern_id)
        category = pat.get('signal', 'neutral')
        generation = pat.get('generation', 0)
        combine = pat.get('combine', 'all')

        # 如果没有 threshold，从 params 自动生成
        if not threshold:
            for atom_cfg in atomics:
                params = atom_cfg.get('params', {})
                if 'min_ratio' in params:
                    threshold['min'] = params['min_ratio']
                if 'max_ratio' in params:
                    threshold['max'] = params['max_ratio']
                if 'min' in params:
                    threshold['min'] = params['min']
                if 'max' in params:
                    threshold['max'] = params['max']

        if debug:
            logger.debug(f"\n   🔍 形态: {human_readable}")
            logger.debug(f"      window={window}, threshold={threshold}, 原子数={len(atomics)}")

        for i in range(window - 1, len(klines)):
            context = {'idx': i, 'ma20': None}

            atom_values = {}
            atom_valid = {}
            atom_instances = {}
            for atom_cfg in atomics:
                atom_class = ATOMIC_CLASSES.get(atom_cfg['class'])
                if not atom_class:
                    continue
                params = atom_cfg.get('params', {})
                atom = atom_class(**params)
                atom_instances[atom_cfg['class']] = atom
                result = atom.check(klines, i, context)
                atom_values[atom_cfg['class']] = result.get('value', 0.0)
                atom_valid[atom_cfg['class']] = result.get('is_valid', False)

            if debug and i == window - 1:
                logger.debug(f"      📌 第 {i} 根K线: atom_values={atom_values}, atom_valid={atom_valid}")

            # 判断每个原子是否满足阈值
            cond_results = []
            for atom_cfg in atomics:
                class_name = atom_cfg['class']
                value = atom_values.get(class_name, 0.0)
                is_valid = atom_valid.get(class_name, False)

                if not is_valid:
                    cond_results.append(False)
                    continue

                matched = True
                if 'min' in threshold and value < threshold['min']:
                    matched = False
                if 'max' in threshold and value > threshold['max']:
                    matched = False
                cond_results.append(matched)

            if combine == 'all':
                matched = all(cond_results)
            else:
                matched = any(cond_results)

            if matched:
                # strength = 各原子归一化后的均值（统一 0~1，跨形态可比）
                norm_values = [
                    atom_instances[c].normalize(atom_values[c])
                    for c in atom_instances if c in atom_values
                ]
                overall_strength = sum(norm_values) / len(norm_values) if norm_values else 0.0

                match_date = klines[i]['date']
                match_price = klines[i]['close']

                # 计算收益率
                r5 = _calc_return(klines, i, 5)
                r10 = _calc_return(klines, i, 10)
                r20 = _calc_return(klines, i, 20)
                composite = calc_composite_return(r5, r10, r20)
                signed = signed_log_score(composite)
                base = calc_base_score(composite)

                # ===== 判断位置是否有效，决定 pending/ready 状态 =====
                # band_position 为 None 或 "unknown" 时，标记为 pending（0）
                # 否则标记为 ready（1）
                is_ready = 1 if band_position is not None and band_position != "unknown" else 0
                updated_at = datetime.now().isoformat() if is_ready else None

                # 写入数据库（含波段峰谷信息、位置标签、pending 状态）
                if write_to_db and symbol != "UNKNOWN":
                    try:
                        write_pattern_history(
                            symbol=symbol,
                            pattern_id=pattern_id,
                            pattern_name=human_readable,
                            category=category,
                            match_date=str(match_date),
                            match_price=match_price,
                            peak_date=peak_date,
                            valley_date=valley_date,
                            band_position=band_position,
                            band_progress=0.0,
                            band_direction=None,
                            wave_id=None,
                            band_position_ready=is_ready,
                            band_position_updated_at=updated_at,
                            return_5d=r5,
                            return_10d=r10,
                            return_20d=r20,
                            composite_return=composite,
                            signed_score=signed,
                            base_score=base,
                            scan_version=1
                        )
                        write_atomic_features(
                            symbol=symbol,
                            date=str(match_date),
                            pattern_id=pattern_id,
                            atom_values=atom_values
                        )
                    except Exception as e:
                        if debug:
                            logger.debug(f"      ⚠️ 写入数据库失败: {e}")

                results.append({
                    "pattern_id": pattern_id,
                    "pattern_type": human_readable,
                    "category": category,
                    "generation": generation,
                    "idx": i,
                    "date": match_date,
                    "strength": round(overall_strength, 4),
                    "meta": {
                        "window": window,
                        "atomics": atom_values,
                        "threshold": threshold,
                        "return_5d": round(r5, 4),
                        "return_10d": round(r10, 4),
                        "return_20d": round(r20, 4),
                        "composite_return": round(composite, 4),
                        "signed_score": round(signed, 4),
                        "base_score": round(base, 4),
                        "peak_date": peak_date,
                        "valley_date": valley_date,
                        "band_position": band_position,
                        "band_position_ready": is_ready,
                    }
                })

                if debug:
                    logger.debug(f"      ✅ 匹配成功! 日期={match_date}, strength={overall_strength:.4f}")
                # 生产扫描：收集片段内全部匹配点（不 break），重复由 data_writer 幂等写入去重

    if debug:
        logger.debug(f"\n   📊 匹配结果总数: {len(results)}")

    # 去重
    if results:
        seen = {}
        for r in results:
            date_key = str(r['date']) if hasattr(r['date'], 'strftime') else str(r['date'])
            key = (date_key, r.get('pattern_id', ''))
            if key not in seen or r['strength'] > seen[key]['strength']:
                seen[key] = r
        results = list(seen.values())
        if debug:
            logger.debug(f"   📊 去重后结果数: {len(results)}")

    # 统一日期格式
    for r in results:
        if hasattr(r['date'], 'strftime'):
            r['date'] = r['date'].strftime('%Y-%m-%d')
        else:
            r['date'] = str(r['date'])

    return results