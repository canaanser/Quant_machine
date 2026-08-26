# -*- coding: utf-8 -*-
"""
形态 × 位置 × 逐日收益 验证脚本
==============================================
验证老板假设：形态的作用域可能在头几天（D+1~D+5），而非 5/10/20 日
复合收益（复合会稀释短期信号）。且必须带位置（band_position）。

方法：
  1. 从 pattern_history 取 (symbol, match_date, band_position, pattern_id)
  2. 从 stockdb / 缓存 拉日线，算 match_date 后 D+1..D+5 逐日收益
  3. 按 band_position × 形态 分组统计逐日收益 + 胜率

用法（Windows，全量 20 只）：
    python tests/validate_daily_return.py --tickers "000063,...,688205" --start 2020-01-01 --end 2026-07-31

结果写入 outputs/daily_return_result.txt
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


def load_daily(tickers, start, end, source):
    """拉取日线（含 open/high/low/close）"""
    md = load_data(source=source, tickers=tickers, start=start, end=end,
                   frequency='1d', fq='qfq')
    return md


def get_ohlc(md, symbol):
    return md.get_ohlc(symbol)


def main():
    parser = argparse.ArgumentParser(description="形态×位置×逐日收益验证")
    parser.add_argument("--tickers", default="000063")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-07-31")
    parser.add_argument("--source", default="freestockdb")
    parser.add_argument("--db", default=None,
                        help="pattern_history 数据库路径（默认 data/index_store/pattern_history.db）")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    # ===== 1. 从 pattern_history 取记录（含位置）=====
    db = args.db or str(PROJECT_ROOT / "data" / "index_store" / "pattern_history.db")
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    recs = cur.execute("""
        SELECT symbol, substr(match_date,1,10), band_position, pattern_name
        FROM pattern_history
        WHERE band_position_ready=1 AND band_position != 'unknown'
    """).fetchall()
    conn.close()
    print(f"✅ pattern_history 记录: {len(recs)} 条（含位置）")

    # ===== 2. 拉日线 =====
    print(f"▶ 加载日线（{len(tickers)} 只, {args.start}~{args.end}）...")
    md = load_daily(tickers, args.start, args.end, args.source)
    print(f"  ✅ 加载完成: {len(md.price.columns)} 只, {len(md.price)} 交易日")

    # 预取每只股票的 ohlc
    ohlc_map = {}
    for sym in set(r[0] for r in recs):
        try:
            o = get_ohlc(md, sym)
            if o is not None and not o.empty:
                ohlc_map[sym] = o
        except Exception:
            continue
    print(f"  ✅ 可用日线股票: {len(ohlc_map)}")

    # ===== 3. 逐日收益统计 =====
    agg = defaultdict(list)  # (band_position, pattern_name) -> [(d1..d5)]
    agg_pos = defaultdict(list)  # band_position -> [(d1..d5)]
    matched = skipped = 0
    for sym, mdate, bp, pname in recs:
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
            if i + 5 >= len(ohlc):
                skipped += 1
                continue
            base = float(ohlc['close'].iloc[i])
            if base <= 0:
                skipped += 1
                continue
            daily = [float(ohlc['close'].iloc[i+j]) / base - 1 for j in range(1, 6)]
            matched += 1
            agg[(bp, pname)].append(daily)
            agg_pos[bp].append(daily)
        except Exception:
            skipped += 1
            continue
    print(f"  ✅ 匹配到日线: {matched} 条, 跳过: {skipped}")

    # ===== 4. 输出 =====
    lines = []
    lines.append("=" * 72)
    lines.append(f"形态 × 位置 × 逐日收益（{tickers} | {args.start}~{args.end}）")
    lines.append(f"样本: {matched} 条（pattern_history 含位置 × 日线匹配）")
    lines.append("=" * 72)

    lines.append("\n【一、位置 × 逐日收益】（所有形态合并，看位置在逐日维度的作用）")
    lines.append(f"{'位置':<12} {'样本':>6} {'D+1':>8} {'D+2':>8} {'D+3':>8} {'D+4':>8} {'D+5':>8} {'D+1胜率':>8}")
    for bp in ['valley', 'rise_lower', 'rise_upper', 'peak', 'fall_upper', 'fall_lower']:
        lst = agg_pos.get(bp, [])
        if len(lst) < 20:
            continue
        arr = np.array(lst)
        row = f"{bp:<12} {len(lst):>6}"
        for j in range(5):
            row += f" {arr[:,j].mean():>8.2%}"
        row += f" {(arr[:,0]>0).mean():>8.0%}"
        lines.append(row)

    lines.append("\n【二、关键位置 × 典型形态 × 逐日收益】")
    lines.append("（底部 valley/rise_lower 与顶部 peak/fall_upper 的对比）")
    for bp in ['valley', 'rise_lower', 'peak', 'fall_upper']:
        lines.append(f"\n  --- {bp} ---")
        for pname in ['乌云盖顶', '十字星', '看涨吞没', '看跌吞没', '射击之星']:
            lst = agg.get((bp, pname), [])
            if len(lst) < 10:
                continue
            arr = np.array(lst)
            row = f"  {pname:<6} n={len(lst):>4}:"
            for j in range(5):
                row += f" D+{j+1}={arr[:,j].mean():+.2%}"
            lines.append(row)

    lines.append("\n【三、十字星 底部 vs 顶部 逐日】（老板关注）")
    for bp, label in [('valley', '底部valley'), ('rise_lower', '底部rise_lower'),
                      ('peak', '顶部peak'), ('fall_upper', '顶部fall_upper')]:
        lst = agg.get((bp, '十字星'), [])
        if len(lst) < 10:
            continue
        arr = np.array(lst)
        row = f"  {label:<14} n={len(lst):>4}:"
        for j in range(5):
            row += f" D+{j+1}={arr[:,j].mean():+.2%}"
        lines.append(row)

    out_path = PROJECT_ROOT / "outputs" / "daily_return_result.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding='utf-8')
    print("\n✅ 完成！结果写入 outputs/daily_return_result.txt")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
