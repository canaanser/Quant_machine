# -*- coding: utf-8 -*-
"""
处境特征 × 典型形态 验证脚本（老板思路）
==============================================
实盘视角：不用精确位置（band_position 是后验），用"实盘可观测的
处境特征"替代位置判断：

  处境特征（截至当日，无未来函数）：
    - 回撤深度：match_price 相对近120日最高点的回撤 %
    - 下跌持续：从最近高点到当前的天数

验证目标：十字星 / 乌云盖顶 在"深回撤处境"下是否有条件价值
（相对"无形态日"或"浅回撤处境"的后续逐日收益差异）

用法（Windows 全量）：
    python tests/validate_situation.py --tickers "000063,...,688205" --start 2020-01-01 --end 2026-07-31
结果写入 outputs/situation_result.txt
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sqlite3
import numpy as np
import pandas as pd
from collections import defaultdict

from core.data_loader import load_data

LOOKBACK = 120  # 回撤计算窗口（近120日高点）


def main():
    parser = argparse.ArgumentParser(description="处境特征×形态验证")
    parser.add_argument("--tickers", default="000063")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-07-31")
    parser.add_argument("--source", default="freestockdb")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    # ===== 1. 从 pattern_history 取记录（十字星/乌云盖顶 + 全形态作对照）=====
    db = str(PROJECT_ROOT / "data" / "index_store" / "pattern_history.db")
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    recs = cur.execute("""
        SELECT symbol, substr(match_date,1,10), match_price, pattern_name
        FROM pattern_history
        WHERE band_position_ready=1 AND match_price IS NOT NULL
    """).fetchall()
    conn.close()
    print(f"✅ pattern_history 记录: {len(recs)} 条")

    # ===== 2. 拉日线 =====
    print(f"▶ 加载日线...")
    md = load_data(source=args.source, tickers=tickers, start=args.start, end=args.end,
                   frequency='1d', fq='qfq')
    print(f"  ✅ {len(md.price.columns)} 只, {len(md.price)} 交易日")

    ohlc_map = {}
    for sym in set(r[0] for r in recs):
        try:
            o = md.get_ohlc(sym)
            if o is not None and not o.empty:
                ohlc_map[sym] = o
        except Exception:
            continue
    print(f"  ✅ 可用日线: {len(ohlc_map)} 只")

    # ===== 3. 算处境特征 + 逐日收益 =====
    # 分组: (形态类, 回撤深度档) -> [逐日收益]
    # 形态类: '十字星' / '乌云盖顶' / '其他形态' / '无(基准:所有记录)'
    # 回撤档: 'deep'(<-20%) / 'mid'(-20%~-10%) / 'shallow'(>-10%)
    agg = defaultdict(list)
    agg_base = defaultdict(list)  # 基准：所有记录按回撤档
    matched = skipped = 0
    for sym, mdate, mprice, pname in recs:
        if sym not in ohlc_map:
            skipped += 1
            continue
        ohlc = ohlc_map[sym]
        try:
            dt = pd.Timestamp(mdate)
            if dt not in ohlc.index:
                skipped += 1
                continue
            i = ohlc.index.get_loc(dt)
            if i + 5 >= len(ohlc) or i < 10:
                skipped += 1
                continue
            base = float(ohlc['close'].iloc[i])
            if base <= 0:
                skipped += 1
                continue
            # 处境特征：近LOOKBACK日最高点回撤
            window = ohlc['close'].iloc[max(0, i - LOOKBACK):i + 1]
            peak = float(window.max())
            drawdown = base / peak - 1 if peak > 0 else 0.0
            # 回撤档
            if drawdown < -0.20:
                dd_band = 'deep'
            elif drawdown < -0.10:
                dd_band = 'mid'
            else:
                dd_band = 'shallow'
            # 形态类
            if '十字星' in pname:
                pat_cls = '十字星'
            elif '乌云' in pname:
                pat_cls = '乌云盖顶'
            else:
                pat_cls = '其他形态'
            # 逐日收益
            daily = [float(ohlc['close'].iloc[i+j]) / base - 1 for j in range(1, 6)]
            matched += 1
            agg[(pat_cls, dd_band)].append(daily)
            agg_base[dd_band].append(daily)
        except Exception:
            skipped += 1
            continue

    # ===== 4. 输出 =====
    lines = []
    lines.append("=" * 76)
    lines.append(f"处境特征 × 形态（回撤深度替代位置，实盘视角）")
    lines.append(f"样本: {matched} 条 | 回撤=近{LOOKBACK}日高点回撤 | 无未来函数")
    lines.append("=" * 76)

    lines.append("\n【基准】所有形态记录按回撤档（无形态区分）")
    lines.append(f"{'回撤档':<10} {'样本':>6} {'D+1':>8} {'D+2':>8} {'D+3':>8} {'D+5':>8} {'D+1胜率':>8}")
    for dd in ['deep', 'mid', 'shallow']:
        lst = agg_base.get(dd, [])
        if len(lst) < 20:
            continue
        arr = np.array(lst)
        lines.append(f"{dd:<10} {len(lst):>6} {arr[:,0].mean():>8.2%} {arr[:,1].mean():>8.2%} "
                     f"{arr[:,2].mean():>8.2%} {arr[:,4].mean():>8.2%} {(arr[:,0]>0).mean():>8.0%}")

    lines.append("\n【形态 × 回撤档】")
    lines.append(f"{'形态':<8} {'回撤档':<10} {'样本':>6} {'D+1':>8} {'D+2':>8} {'D+3':>8} {'D+5':>8} {'D+1胜率':>8}")
    for pat in ['十字星', '乌云盖顶', '其他形态']:
        for dd in ['deep', 'mid', 'shallow']:
            lst = agg.get((pat, dd), [])
            if len(lst) < 10:
                continue
            arr = np.array(lst)
            lines.append(f"{pat:<8} {dd:<10} {len(lst):>6} {arr[:,0].mean():>8.2%} {arr[:,1].mean():>8.2%} "
                         f"{arr[:,2].mean():>8.2%} {arr[:,4].mean():>8.2%} {(arr[:,0]>0).mean():>8.0%}")

    lines.append("\n【关键对比】深回撤处境的形态价值")
    lines.append("（若 十字星/乌云盖顶 在 deep 档显著异于 基准deep → 形态有条件价值）")
    base_deep = np.array(agg_base.get('deep', []))
    if len(base_deep) > 20:
        for pat in ['十字星', '乌云盖顶']:
            lst = agg.get((pat, 'deep'), [])
            if len(lst) < 10:
                continue
            arr = np.array(lst)
            diff = arr[:, 0].mean() - base_deep[:, 0].mean()
            lines.append(f"  {pat}@deep: D+1={arr[:,0].mean():+.2%} vs 基准deep D+1={base_deep[:,0].mean():+.2%} "
                         f"→ 差异 {diff:+.2%}")

    out_path = PROJECT_ROOT / "outputs" / "situation_result.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding='utf-8')
    print("\n✅ 完成！结果写入 outputs/situation_result.txt")


if __name__ == "__main__":
    main()
