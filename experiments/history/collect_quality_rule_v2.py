# -*- coding: utf-8 -*-
"""
质量评分 v2 规则验证（84 只全量 + 时间分片 + 位置维度）
=====================================================================
2026-08-28 小二陈（老板周末大干第2项）：
  v1 规则"深跌<-20%+放量>0.7"= 样本外65.1%/Sharpe2.18，已定型进策略层。
  20只池验证发现位置维度更强：深跌+放量+距250日高点<-40% = 69.2%；
  +250日区间分位<0.15 = 72.0%。本脚本在 84 只全量上走防过拟合闸门：
  1. 样本内（2017-2021）网格扫描：v1阈值 × 位置阈值
  2. 样本外（2022-2026）验证
  3. 输出 v1 vs v2 对比

用法（Windows，需 stockdb.exe 服务）：
    cd E:/stockgate/Quant_Alpha_System
    python scripts/collect_quality_rule_v2.py
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

from core.data_loader import load_data
from core.strategy import SimpleStrategy
import config.config as config_mod

START, END = '2017-01-01', '2026-08-27'
SPLIT = '2022-01-01'
DEFAULT_TICKERS = list(config_mod.SCAN_TICKERS)


def collect_signals(md) -> pd.DataFrame:
    """收集 Simple 信号 + 特征（深跌/量比/位置）"""
    price = md.price
    returns = price.pct_change(fill_method=None).dropna(how='all')
    s = SimpleStrategy(5, 20)
    s.prepare(returns, None)
    recs = []
    t0 = time.time()
    for i in range(42, len(returns)):
        sc = s._score_from_features(returns.iloc[:i])
        date_s = returns.index[i - 1]
        for code, v in sc.items():
            if v <= 0 or code not in price.columns:
                continue
            pcol = price[code].dropna()
            if date_s not in pcol.index:
                continue
            i0 = pcol.index.get_loc(date_s)
            if i0 < 250 or i0 + 11 >= len(pcol):
                continue
            close = pcol.iloc[i0]
            deep20 = close / pcol.iloc[i0 - 20] - 1
            win = pcol.iloc[i0 - 250:i0 + 1]
            pct_250d_high = close / win.max() - 1
            rng = win.max() - win.min()
            range_pct_250 = (close - win.min()) / rng if rng > 0 else np.nan
            vol_ratio = np.nan
            try:
                vol = md.volume[code].dropna()
                if date_s in vol.index:
                    j0 = vol.index.get_loc(date_s)
                    vmean = vol.iloc[max(0, j0 - 20):j0].mean()
                    vol_ratio = vol.iloc[j0] / vmean if vmean > 0 else np.nan
            except Exception:
                pass
            r5 = pcol.iloc[i0 + 6] / pcol.iloc[i0 + 1] - 1
            r10 = pcol.iloc[i0 + 11] / pcol.iloc[i0 + 1] - 1
            recs.append(dict(code=code, date=date_s, score=v, deep20=deep20,
                             vol_ratio=vol_ratio, pct_250d_high=pct_250d_high,
                             range_pct_250=range_pct_250, r5=r5, r10=r10))
        if i % 400 == 0:
            print(f"  ... 扫描至 {date_s.date()} 已收集 {len(recs)}，耗时 {time.time()-t0:.0f}s", flush=True)
    print(f"✅ 信号收集完成：{len(recs)}，耗时 {time.time()-t0:.0f}s")
    return pd.DataFrame(recs)


def report(name, g):
    if len(g) < 30:
        print(f"{name}: 样本不足 {len(g)}")
        return
    sh = np.mean(g.r10) / np.std(g.r10) * np.sqrt(252 / 10) if np.std(g.r10) > 0 else 0
    print(f"{name}: {len(g)}笔 5日胜率{np.mean(g.r5>0):.1%} 10日胜率{np.mean(g.r10>0):.1%} "
          f"10日均值{np.mean(g.r10):+.2%} 10日Sharpe≈{sh:.2f}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="质量评分v2规则验证（84只全量+位置维度）")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    print(f"🚀 数据加载：{len(tickers)} 只 ...")
    md = load_data(source='freestockdb', tickers=tickers,
                   start=args.start, end=args.end, frequency='1d', fq='qfq')
    print(f"✅ 加载完成 {md.price.shape[0]} 交易日")

    df = collect_signals(md)
    out = PROJECT_ROOT / 'outputs' / 'signal_features_v2.csv'
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f"💾 已存: {out}")

    train = df[df['date'] < SPLIT]
    test = df[df['date'] >= SPLIT]
    print(f"\n总 {len(df)} | 样本内 {len(train)} | 样本外 {len(test)}")
    report("样本内基线", train)
    report("样本外基线", test)

    # 阶段1：v1 网格（deep20 × vol_ratio）样本内找最优
    print("\n===== 阶段1：v1 网格（样本内）=====")
    best_v1 = None
    for dt in [-0.10, -0.15, -0.20]:
        for vr in [0.7, 1.0]:
            g = train[(train.deep20 < dt) & (train.vol_ratio > vr)]
            if len(g) >= 300:
                wr = np.mean(g.r10 > 0)
                if best_v1 is None or wr > best_v1['wr']:
                    best_v1 = {'wr': wr, 'dt': dt, 'vr': vr, 'n': len(g)}
    print(f"v1最优：深跌<{best_v1['dt']:.0%} 放量>{best_v1['vr']:.1f} 样本内 {best_v1['n']}笔 {best_v1['wr']:.1%}")

    # 阶段2：v1 + 位置阈值扫描
    print("\n===== 阶段2：v1+位置 扫描（样本内）=====")
    best_v2 = None
    for ph in [-0.30, -0.35, -0.40, -0.45, -0.50]:
        for rp in [0.10, 0.15, 0.20]:
            g = train[(train.deep20 < best_v1['dt']) & (train.vol_ratio > best_v1['vr']) &
                      ((train.pct_250d_high < ph) | (train.range_pct_250 < rp))]
            if len(g) >= 200:
                wr = np.mean(g.r10 > 0)
                if best_v2 is None or wr > best_v2['wr']:
                    best_v2 = {'wr': wr, 'ph': ph, 'rp': rp, 'n': len(g)}
    if best_v2 is None:
        print("⚠️ 样本内无满足条件的 v2 规则")
        return
    print(f"v2最优：距250日高点<-{abs(best_v2['ph']):.0%} 或 区间分位<{best_v2['rp']:.0%} "
          f"样本内 {best_v2['n']}笔 {best_v2['wr']:.1%}")

    # 样本外验证
    print("\n===== 样本外验证（防过拟合闸门）=====")
    m1 = lambda d: (d.deep20 < best_v1['dt']) & (d.vol_ratio > best_v1['vr'])
    m2 = lambda d: m1(d) & ((d.pct_250d_high < best_v2['ph']) | (d.range_pct_250 < best_v2['rp']))
    report("v1-样本内", train[m1(train)])
    report("v1-样本外", test[m1(test)])
    report("v2-样本内", train[m2(train)])
    report("v2-样本外", test[m2(test)])
    report("v2-全样本", df[m2(df)])


if __name__ == "__main__":
    main()
