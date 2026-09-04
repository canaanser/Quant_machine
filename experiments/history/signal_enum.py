# -*- coding: utf-8 -*-
"""
信号穷举器（signal enumerator）——质量规则全网格搜索 + 五道防过拟合闸门
=====================================================================
2026-08-28 小二陈（老板周末大干第4项，含老板补充的三个优化方向）：

思路：质量评分从"手工找规则"升级为"机器全扫"。以 Simple 信号池为母池，
网格穷举「深跌 × 放量 × 位置 × 冷却期」所有阈值组合，用五道闸门筛出
真正稳健（且未过拟合）的规则，聚类去重后输出 Top 榜。

五道闸门（含老板补充）：
  预处理：规则聚类（命中信号集合 Jaccard≥0.8 归簇，每簇选 Sharpe 最高代表）
  闸1 样本量：总信号 ≥300
  闸2 时间分片：样本内(2017-2021)找 → 样本外(2022-2026)验，胜率衰减≤5点且样本外≥58%
  闸3 年度稳定：≥7/10 有效年正收益（弱年信号<20 跳过，不计入有效年）
  闸4 衰减斜率：近3年(2023-2025) vs 前5年(2017-2021) 胜率衰减 >8点 → 衰退标记
  闸5 Top 榜聚类去重（每簇一个代表）

用法（Windows 有 signal_features_v2.csv 后）：
    cd E:/stockgate/Quant_Alpha_System
    python -B scripts/signal_enum.py [--pool outputs/signal_features_v2.csv] [--workers 8]
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import numpy as np
import pandas as pd

SPLIT = '2022-01-01'          # 样本内/外分界
MIN_SAMPLES = 300             # 闸1：总样本
OOS_MIN_WIN = 0.58            # 闸2：样本外最低胜率
OOS_MAX_DECAY = 0.05          # 闸2：样本内→样本外衰减上限
MIN_EFFECTIVE_YEARS = 7       # 闸3：有效年数下限
GOOD_YEAR_RATIO = 0.70        # 闸3：正收益有效年比例
YEAR_MIN_SIGNALS = 20         # 弱年：年度信号<20 跳过
DECAY_WINDOW = (2017, 2021)   # 闸4：前5年
RECENT_WINDOW = (2023, 2025)  # 闸4：近3年（2026 数据不完整不计）
MAX_RECENT_DECAY = 0.08       # 闸4：近3年较前5年衰减上限
JACCARD_THRESHOLD = 0.80      # 聚类：规则信号集 Jaccard 归簇阈值

# 网格
DEEP_GRID = [-0.10, -0.15, -0.20, -0.25, -0.30]
VOL_GRID = [0.5, 0.7, 0.9, 1.0, 1.2]
POS_HIGH_GRID = [None, -0.30, -0.40, -0.50]   # None=位置不限
COOLDOWN_GRID = [0, 5, 10, 20]


def load_pool(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])
    df['year'] = df['date'].dt.year
    return df


def apply_rule(df: pd.DataFrame, deep: float, vol: float, pos_high, cooldown: int) -> pd.DataFrame:
    """应用规则：深跌/放量/位置过滤 + 冷却期（同股信号间隔≥cooldown天，保留首个）"""
    m = (df['deep20'] < deep) & (df['vol_ratio'] > vol)
    if pos_high is not None:
        m = m & (df['pct_250d_high'] < pos_high)
    sub = df[m].copy()
    if cooldown > 0 and len(sub) > 0:
        sub = sub.sort_values(['code', 'date'])
        keep = []
        last_date = {}
        for _, r in sub.iterrows():
            c = r['code']
            if c not in last_date or (r['date'] - last_date[c]).days >= cooldown:
                keep.append(r.name)
                last_date[c] = r['date']
        sub = sub.loc[keep]
    return sub


def yearly_win(sub: pd.DataFrame):
    """分年胜率/样本数"""
    by = {}
    for y, g in sub.groupby('year'):
        if len(g) > 0:
            by[y] = (len(g), np.mean(g['r10'] > 0))
    return by


def evaluate_rule(df: pd.DataFrame, deep: float, vol: float, pos_high, cooldown: int) -> dict:
    sub = apply_rule(df, deep, vol, pos_high, cooldown)
    n = len(sub)
    if n < MIN_SAMPLES:
        return {'deep': deep, 'vol': vol, 'pos': pos_high, 'cd': cooldown, 'ok': False, 'reason': f'样本{n}<{MIN_SAMPLES}'}
    train = sub[sub['date'] < SPLIT]
    test = sub[sub['date'] >= SPLIT]
    if len(train) < 100 or len(test) < 100:
        return {'deep': deep, 'vol': vol, 'pos': pos_high, 'cd': cooldown, 'ok': False, 'reason': '分片样本不足'}
    tr_w = np.mean(train['r10'] > 0)
    te_w = np.mean(test['r10'] > 0)
    # 闸2
    if te_w < OOS_MIN_WIN or (tr_w - te_w) > OOS_MAX_DECAY:
        return {'deep': deep, 'vol': vol, 'pos': pos_high, 'cd': cooldown, 'ok': False,
                'reason': f'闸2: 样本外{te_w:.1%}或衰减{tr_w-te_w:+.1%}'}
    # 闸3：年度稳定（弱年跳过）
    yw = yearly_win(sub)
    eff_years = [y for y, (cnt, w) in yw.items() if cnt >= YEAR_MIN_SIGNALS]
    good_years = [y for y in eff_years if yw[y][1] > 0.5]
    if len(eff_years) < MIN_EFFECTIVE_YEARS or len(good_years) / len(eff_years) < GOOD_YEAR_RATIO:
        return {'deep': deep, 'vol': vol, 'pos': pos_high, 'cd': cooldown, 'ok': False,
                'reason': f'闸3: 有效年{len(eff_years)} 正收益{len(good_years)}/{len(eff_years)}'}
    # 闸4：衰减斜率
    d_lo, d_hi = DECAY_WINDOW
    r_lo, r_hi = RECENT_WINDOW
    early = [yw[y][1] for y in range(d_lo, d_hi + 1) if y in yw and yw[y][0] >= YEAR_MIN_SIGNALS]
    recent = [yw[y][1] for y in range(r_lo, r_hi + 1) if y in yw and yw[y][0] >= YEAR_MIN_SIGNALS]
    decay = 0.0
    if early and recent:
        decay = np.mean(early) - np.mean(recent)
    decaying = decay > MAX_RECENT_DECAY
    # Sharpe（10日）
    sh = np.mean(sub['r10']) / np.std(sub['r10']) * np.sqrt(252 / 10) if np.std(sub['r10']) > 0 else 0
    return {'deep': deep, 'vol': vol, 'pos': pos_high, 'cd': cooldown, 'ok': True,
            'n': n, 'train_w': tr_w, 'test_w': te_w, 'decay': decay, 'decaying': decaying,
            'sharpe': sh, 'mean10': np.mean(sub['r10']), 'years': len(eff_years), 'good_years': len(good_years)}


def jaccard(sig_a: set, sig_b: set) -> float:
    inter = len(sig_a & sig_b)
    union = len(sig_a | sig_b)
    return inter / union if union > 0 else 0.0


def cluster_rules(passed: list, df: pd.DataFrame):
    """闸5：按命中信号集合 Jaccard 归簇，每簇选 Sharpe 最高代表"""
    sigs = {}
    for r in passed:
        sub = apply_rule(df, r['deep'], r['vol'], r['pos'], r['cd'])
        sigs[id(r)] = set(sub['code'].astype(str) + '_' + sub['date'].astype(str))
    clusters = []
    for r in passed:
        placed = False
        for cl in clusters:
            rep = cl[0]
            j = jaccard(sigs[id(r)], sigs[id(rep)])
            if j >= JACCARD_THRESHOLD:
                cl.append(r)
                placed = True
                break
        if not placed:
            clusters.append([r])
    # 每簇选 Sharpe 最高代表
    reps = [max(cl, key=lambda x: x['sharpe']) for cl in clusters]
    for cl in clusters:
        reps[-1]  # noop
    return reps, clusters


def main():
    import argparse
    parser = argparse.ArgumentParser(description="信号穷举器（五道闸门）")
    parser.add_argument("--pool", default=str(PROJECT_ROOT / 'outputs' / 'signal_features_v2.csv'))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()

    pool = Path(args.pool)
    if not pool.exists():
        print(f"❌ 母池不存在: {pool}\n   请先运行 scripts/collect_quality_rule_v2.py 生成 signal_features_v2.csv")
        return
    print(f"🚀 加载母池: {pool}")
    df = load_pool(str(pool))
    print(f"✅ 母池 {len(df)} 信号（{df['year'].min()}-{df['year'].max()}）")

    # 生成网格
    grid = [(d, v, p, c) for d in DEEP_GRID for v in VOL_GRID for p in POS_HIGH_GRID for c in COOLDOWN_GRID]
    print(f"🔍 网格 {len(grid)} 个规则组合，多进程 {args.workers} ...")
    t0 = time.time()

    results = []
    if args.workers > 1:
        import multiprocessing as mp
        with mp.Pool(args.workers) as pool_:
            results = pool_.starmap(evaluate_rule, [(df, d, v, p, c) for d, v, p, c in grid])
    else:
        results = [evaluate_rule(df, d, v, p, c) for d, v, p, c in grid]

    passed = [r for r in results if r.get('ok')]
    print(f"✅ 评估完成 耗时 {time.time()-t0:.0f}s：通过 {len(passed)}/{len(grid)}")

    if not passed:
        print("⚠️ 无规则通过五道闸门——网格需要放宽或母池信号不足")
        return

    # 聚类去重
    reps, clusters = cluster_rules(passed, df)
    reps.sort(key=lambda x: -x['sharpe'])
    print(f"\n===== Top 规则榜（聚类后 {len(reps)} 簇代表）=====")
    print(f"{'深跌':>6}{'放量':>6}{'位置':>8}{'冷却':>5}{'样本':>7}{'样本内':>8}{'样本外':>8}{'Sharpe':>8}{'衰减':>7}{'正年':>6}{'衰退?':>6}")
    for r in reps[:args.top]:
        pos = '不限' if r['pos'] is None else f"<-{abs(r['pos']):.0%}"
        print(f"{r['deep']:>6.0%}{r['vol']:>6.1f}{pos:>8}{r['cd']:>5d}{r['n']:>7d}"
              f"{r['train_w']:>8.1%}{r['test_w']:>8.1%}{r['sharpe']:>8.2f}{r['decay']:>7.1%}"
              f"{r['good_years']}/{r['years']}{'⚠️' if r['decaying'] else '':>6}")

    print("\n===== 衰退规则（通过前四闸但近3年衰减>8%）=====")
    decayed = [r for r in passed if r.get('decaying')]
    for r in decayed[:10]:
        print(f"  深跌{r['deep']:.0%} 放量{r['vol']:.1f} 位置{r['pos']} 冷却{r['cd']} "
              f"样本内{r['train_w']:.1%}→样本外{r['test_w']:.1%} 近3年衰减{r['decay']:+.1%}")


if __name__ == "__main__":
    main()
