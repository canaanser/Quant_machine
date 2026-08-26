# -*- coding: utf-8 -*-
"""
V3 新库回填脚本（2026-08-27 小二陈）
=============================================
从日线重算并写入新库 pattern_history_v3.db：
  1. trendline_nodes  ：自研 swing 识别（3σ 动态阈值 + 交替锚点）
  2. bollinger_states ：逐日布林带状态
  3. pattern_history  ：旧记录回填新字段（逐日收益/处境/颜色）

用法（Windows 全量 / WSL 缓存验证）：
    python scripts/backfill_v3.py --tickers 000063,601728 --start 2025-01-01 --end 2026-07-31
    python scripts/backfill_v3.py --tickers "000063,...,688205" --start 2020-01-01 --end 2026-07-31
"""
import argparse
import sys
import uuid
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from core.data_loader import load_data
from structure_engine.scanner.data_writer.schema_v3 import (
    CREATE_TRENDLINE_NODES, CREATE_BOLLINGER_STATES, CREATE_PATTERN_HISTORY,
)

NEW_DB = PROJECT_ROOT / "data" / "index_store" / "pattern_history_v3.db"
SCAN_VERSION = 1


# ===== 1. 自研 swing 识别（吸收 leoi137 3σ + pytrendline 归并） =====
def detect_swings(ohlc, mult=1.2, window=10):
    """识别显著 swing 点（peak/valley 交替出现）
    阈值 = 150日对数收益波动率 × mult；局部窗口 ±window 根"""
    close = ohlc['close'].astype(float)
    log_ret = np.log(close / close.shift(1))
    vol = log_ret.rolling(window=150).std().mean() * 100
    if np.isnan(vol) or vol <= 0:
        return []
    thr = vol * mult
    swings = []
    kind = None
    i = 160
    while i < len(close) - window:
        cur = close.iloc[i]
        left = close.iloc[i-window:i]
        right = close.iloc[i+1:i+1+window]
        if len(left) < 3 or len(right) < 3:
            i += 1
            continue
        is_peak = cur >= left.max() - 1e-9 and cur >= right.max() - 1e-9
        is_valley = cur <= left.min() + 1e-9 and cur <= right.min() + 1e-9
        if is_peak:
            rise = (cur / left.min() - 1) * 100 if left.min() > 0 else 0
            fall = (cur / right.min() - 1) * 100 if right.min() > 0 else 0
            if rise > thr and fall > thr and kind != 'peak':
                swings.append((close.index[i], float(cur), 'peak'))
                kind = 'peak'
                i += window
                continue
        if is_valley:
            fall = (left.max() / cur - 1) * 100 if cur > 0 else 0
            rise = (right.max() / cur - 1) * 100 if cur > 0 else 0
            if fall > thr and rise > thr and kind != 'valley':
                swings.append((close.index[i], float(cur), 'valley'))
                kind = 'valley'
                i += window
                continue
        i += 1
    return swings


# ===== 2. 布林带逐日状态 =====
def calc_bollinger(ohlc, period=20, std_mult=2.0):
    close = ohlc['close'].astype(float)
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    bandwidth = (upper - lower) / mid
    position = (close - lower) / (upper - lower)
    # squeeze：带宽 < 历史20%分位
    bws = bandwidth.dropna()
    if len(bws) > 20:
        sq_thr = bws.quantile(0.20)
        squeeze = (bandwidth < sq_thr).astype(int)
    else:
        squeeze = pd.Series(0, index=close.index)
    upper_break = (close >= upper).astype(int)
    lower_break = (close <= lower).astype(int)
    return mid, upper, lower, bandwidth, position, squeeze, upper_break, lower_break


def main():
    parser = argparse.ArgumentParser(description="V3新库回填")
    parser.add_argument("--tickers", default="000063,601728")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-07-31")
    parser.add_argument("--source", default="stockdb_http")
    args = parser.parse_args()
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    # 建新库表（幂等）
    conn = sqlite3.connect(str(NEW_DB))
    for ddl in [CREATE_PATTERN_HISTORY, CREATE_TRENDLINE_NODES, CREATE_BOLLINGER_STATES]:
        conn.execute(ddl)
    conn.commit()

    # 拉日线
    print(f"▶ 加载日线（{len(tickers)} 只, {args.start}~{args.end}）...")
    md = load_data(source=args.source, tickers=tickers, start=args.start, end=args.end,
                   frequency='1d', fq='qfq')
    print(f"  ✅ {len(md.price.columns)} 只, {len(md.price)} 交易日")

    tl_count = bs_count = 0
    for sym in tickers:
        try:
            ohlc = md.get_ohlc(sym)
            if ohlc is None or ohlc.empty:
                print(f"  ⚠️ {sym} 无数据，跳过")
                continue
        except Exception:
            continue

        # ---- 2a. 趋势线节点 ----
        swings = detect_swings(ohlc)
        for dt, price, ntype in swings:
            node_id = f"NODE-{sym}-{dt.strftime('%Y%m%d')}-{ntype[:1]}"
            conn.execute("""INSERT OR IGNORE INTO trendline_nodes
                (node_id, symbol, node_date, node_price, node_type,
                 significance, shadow_exceed, cluster_size, wave_id,
                 related_pattern_id, scan_version, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (node_id, sym, dt.strftime('%Y-%m-%d'), price, ntype,
                 1.2, 0.0, 1, None, None, SCAN_VERSION,
                 datetime.now().isoformat()))
            tl_count += 1

        # ---- 2b. 布林带状态 ----
        mid, upper, lower, bw, pos, sq, ub, lb = calc_bollinger(ohlc)
        for d in ohlc.index:
            conn.execute("""INSERT OR REPLACE INTO bollinger_states
                (symbol, bdate, middle, upper, lower, bandwidth, position,
                 upper_break, lower_break, squeeze, scan_version)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (sym, d.strftime('%Y-%m-%d'),
                 None if pd.isna(mid.get(d)) else float(mid[d]),
                 None if pd.isna(upper.get(d)) else float(upper[d]),
                 None if pd.isna(lower.get(d)) else float(lower[d]),
                 None if pd.isna(bw.get(d)) else float(bw[d]),
                 None if pd.isna(pos.get(d)) else float(pos[d]),
                 int(ub.get(d, 0)), int(lb.get(d, 0)), int(sq.get(d, 0)),
                 SCAN_VERSION))
            bs_count += 1
        conn.commit()
        print(f"  ✅ {sym}: swing {len(swings)} 节点, 布林带 {len(ohlc)} 天")

    print(f"\n✅ 回填完成: trendline_nodes +{tl_count}, bollinger_states +{bs_count}")
    print(f"   新库: {NEW_DB}")
    conn.close()


if __name__ == "__main__":
    main()
