# -*- coding: utf-8 -*-
"""
20 年框架下"首现"真伪验证（2026-08-28 小二陈）

背景：扫描已扩到 2006 起（84 只 20 年），"首现"（cooldown IS NULL）现在有完整历史参照。
问题：2016 年起点的"首现 70%"是数据截断伪影还是真信号？
方法：
  1. 首现+4条件（深跌+缩量+大实体短影）按年份分布
  2. 2009+ 的首现（有 2006-2008 历史参照 = 真"近3年+没出现过"）胜率
  3. 冷却分档对照（确认是否只有"首现"特殊）
  4. 深跌+缩量+反转（无首现）全期对照

用法（Windows）：python scripts/verify_first_20y.py
"""
import sys, sqlite3
from pathlib import Path
from collections import defaultdict

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
DB = PROJECT / "data" / "index_store" / "pattern_history.db"


def main():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    atomic = {}
    for s, d, p, vs, br, sr in conn.execute(
            'SELECT symbol, date, pattern_id, volume_spike, body_ratio, shadow_ratio FROM atomic_features'):
        atomic[(s, p, d)] = (vs, br, sr)
    recs = []
    for s, p, dt, dd, cd, r5 in conn.execute(
            'SELECT symbol, pattern_id, substr(match_date,1,10), drawdown_from_peak, cooldown_days, return_5d '
            'FROM pattern_history WHERE return_5d IS NOT NULL'):
        a = atomic.get((s, p, dt))
        if a:
            recs.append((s, dt, dd, cd, r5, a[0], a[1], a[2]))
    conn.close()
    print('联表总数:', len(recs))
    print('日期范围:', min(r[1] for r in recs), '~', max(r[1] for r in recs))


    def ok4(r):
        """深跌+缩量+大实体+短下影（4条件，无首现要求）"""
        return (r[2] is not None and r[2] < -0.20 and r[5] is not None and r[5] <= 0.1
                and r[6] is not None and r[6] >= 0.5 and r[7] is not None and r[7] <= 0.35)


    def stat(name, lst):
        if not lst:
            print(f'{name:<30} 无样本')
            return
        a = np.array([r[4] for r in lst])
        print(f'{name:<30} 样本={len(a):>7} 胜率={np.mean(a > 0):>6.1%} 5日均={np.mean(a):>+7.2%}')


    # ===== 1. 首现+4条件 按年份 =====
    first = [r for r in recs if r[3] is None and ok4(r)]
    print(f'\n首现+4条件 总数: {len(first)}')
    by_year = defaultdict(list)
    for r in first:
        by_year[r[1][:4]].append(r[4])
    print('按年份:')
    for y in sorted(by_year):
        a = np.array(by_year[y])
        print(f'  {y}: n={len(a):>4} 胜率={np.mean(a > 0):>6.1%} 5日均={np.mean(a):>+7.2%}')

    # ===== 2. 2009+ 首现（有 2006-2008 参照） =====
    print()
    stat('首现 2009+（有历史参照）', [r for r in first if r[1] >= '2009-01-01'])
    stat('首现 2006-2008（起点区）', [r for r in first if r[1] < '2009-01-01'])

    # ===== 3. 冷却分档对照（4条件基础） =====
    base = [r for r in recs if ok4(r)]
    print()
    stat('4条件 全部', base)
    stat('  +首现(NULL)', [r for r in base if r[3] is None])
    stat('  +冷却1-30天', [r for r in base if r[3] is not None and r[3] < 30])
    stat('  +冷却30-250天', [r for r in base if r[3] is not None and 30 <= r[3] < 250])
    stat('  +冷却250天+', [r for r in base if r[3] is not None and r[3] >= 250])

    # ===== 4. 4条件（无首现）2017+ 对照 =====
    print()
    stat('4条件 2017+（排除一切起点区）', [r for r in base if r[1] >= '2017-01-01'])
    stat('首现 2017+（20年框架下的真首现）', [r for r in first if r[1] >= '2017-01-01'])

    print('\n✅ 判定：若"首现2017+"（有14年历史参照）仍显著>4条件基准 → 首现是真信号；若≈ → 彻底证伪')


if __name__ == "__main__":
    main()
