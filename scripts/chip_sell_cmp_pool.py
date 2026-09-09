# -*- coding: utf-8 -*-
"""方向池24只 × 三版卖法对比, 2024-01-01 起 (筹码预热数据 2021+ 仅作lookback)
输出: 每票每版净值/笔数/胜率 → 汇总均值 → CSV 明细
用法(Windows): python -B scripts/chip_sell_cmp_pool.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from chip_zte_sell_cmp import run_one, START

START = "20240101"  # noqa: 确保全局

def main():
    from core.data_loader.freestockdb import fetch_daily_qfq_single
    pool = [c.strip() for c in
            open(Path(__file__).parent.parent / "data/tickers/research_direction.txt").read().split(",")
            if c.strip()]
    modes = ['A糙', 'B成熟', 'C死叉即走']
    agg = {m: {'nav': [], 'n': [], 'win': []} for m in modes}
    rows = []
    for code in pool:
        df = fetch_daily_qfq_single(code, "2021-01-01", "2026-12-31")
        if df is None or len(df) < 400:
            print(f"{code}: 数据不足, 跳过", flush=True)
            continue
        line = [code]
        for m in modes:
            trades, nav = run_one(df, 0.85, m)
            rets = np.array([t[6] for t in trades]) if trades else np.array([])
            win = (rets > 0).mean() * 100 if len(rets) else 0.0
            agg[m]['nav'].append(nav)
            agg[m]['n'].append(len(trades))
            agg[m]['win'].append(win)
            line.append(f"{nav:.3f}")
            line.append(str(len(trades)))
        rows.append(line)
        print(f"{code}: A净{line[1]}({line[2]}笔) B净{line[3]}({line[4]}笔) C净{line[5]}({line[6]}笔)", flush=True)
    print("\n===== 汇总(2024-01至今, 24只平均) =====")
    for m in modes:
        navs = agg[m]['nav']
        g = np.array(navs)
        geo = float(np.exp(np.mean(np.log(np.clip(g, 1e-9, None)))))
        print(f"[{m}] 平均净值 {geo:.3f} ({(geo-1)*100:+.0f}%) | "
              f"算术均 {g.mean():.2f} | 中位 {np.median(g):.2f} | "
              f"盈利票 {(g > 1).mean()*100:.0f}% | 总笔数 {sum(agg[m]['n'])} | "
              f"平均胜率 {np.mean(agg[m]['win']):.0f}%")

if __name__ == "__main__":
    main()
