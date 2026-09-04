# -*- coding: utf-8 -*-
"""
事前质量评分规则验证器（84 只全量 + 时间分片）
=====================================================================
2026-08-28 小二陈（老板拍板：先测试，验证通过再上策略层）

背景：Simple 原始评分是"跌势强度"噪声，无质量区分力（分层验证：各分数段
胜率均 ~51%）。20 只池原型发现：信号特征"深跌>10% + 放量>1.0"子集
10 日胜率 61.2%（309 笔）。本脚本在 84 只主池全量验证：
  1. 收集 Simple 所有买入信号 + 信号日特征 + 后续收益
  2. 样本内（2017-2021）网格扫描找最优规则（样本≥300）
  3. 样本外（2022-2026）验证该规则（防过拟合闸门）

用法（Windows，需 stockdb.exe 服务）：
    cd E:/stockgate/Quant_Alpha_System
    python scripts/collect_quality_rule.py

输出：
    outputs/signal_features_full.csv —— 全量信号特征
    控制台 —— 样本内最优规则 + 样本外验证报告
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
from core.backtest import BacktestPipeline
from core.strategy import SimpleStrategy
import config.config as config_mod

START, END = '2017-01-01', '2026-08-27'
SPLIT = '2022-01-01'  # 样本内/外分界
DEFAULT_TICKERS = list(config_mod.SCAN_TICKERS)


def collect_signals(md) -> pd.DataFrame:
    """跑 Simple 收集所有买入信号 + 特征 + 后续收益"""
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
            if i0 < 20 or i0 + 11 >= len(pcol):
                continue
            close = pcol.iloc[i0]
            deep20 = close / pcol.iloc[i0 - 20] - 1
            # 量比/实体/影线：用全字段矩阵（按日期对齐）
            vol_ratio = body = shadow = ma20_dev = np.nan
            try:
                vol = md.volume[code].dropna()
                if date_s in vol.index:
                    j0 = vol.index.get_loc(date_s)
                    vmean = vol.iloc[max(0, j0 - 20):j0].mean()
                    vol_ratio = vol.iloc[j0] / vmean if vmean > 0 else np.nan
                op = md.open_price[code].dropna()
                hi = md.high_price[code].dropna()
                lo = md.low_price[code].dropna()
                if date_s in op.index and date_s in hi.index and date_s in lo.index:
                    o, h, l = op.loc[date_s], hi.loc[date_s], lo.loc[date_s]
                    body = abs(close - o) / o if o > 0 else np.nan
                    rng = h - l
                    shadow = (rng - abs(close - o)) / rng if rng > 0 else np.nan
                ma20 = pcol.iloc[max(0, i0 - 19):i0 + 1].mean()
                ma20_dev = close / ma20 - 1 if ma20 > 0 else np.nan
            except Exception:
                pass
            # 后续收益（信号日次日收盘买入，盘尾模型）
            r5 = pcol.iloc[i0 + 6] / pcol.iloc[i0 + 1] - 1
            r10 = pcol.iloc[i0 + 11] / pcol.iloc[i0 + 1] - 1
            recs.append(dict(code=code, date=date_s, score=v, deep20=deep20,
                             vol_ratio=vol_ratio, body=body, shadow=shadow,
                             ma20_dev=ma20_dev, r5=r5, r10=r10))
        if i % 400 == 0:
            print(f"  ... 扫描至 {date_s.date()} 已收集 {len(recs)} 信号，耗时 {time.time()-t0:.0f}s", flush=True)
    print(f"✅ 信号收集完成：{len(recs)} 个，耗时 {time.time()-t0:.0f}s")
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
    parser = argparse.ArgumentParser(description="事前质量评分规则验证（84只全量+时间分片）")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()]
    print(f"🚀 数据加载：{len(tickers)} 只，{args.start} ~ {args.end} ...")
    t0 = time.time()
    md = load_data(source='freestockdb', tickers=tickers,
                   start=args.start, end=args.end, frequency='1d', fq='qfq')
    print(f"✅ 加载完成 {md.price.shape[0]} 交易日，耗时 {time.time()-t0:.1f}s")

    df = collect_signals(md)
    out = PROJECT_ROOT / 'outputs' / 'signal_features_full.csv'
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f"💾 全量信号特征已存: {out}")

    train = df[df['date'] < SPLIT].copy()
    test = df[df['date'] >= SPLIT].copy()
    print(f"\n总信号 {len(df)} | 样本内 {len(train)}（<{SPLIT}）| 样本外 {len(test)}（≥{SPLIT}）")
    print("\n===== 基线（全部信号）=====")
    report("样本内基线", train)
    report("样本外基线", test)

    # 网格扫描（样本内找最优规则）
    print("\n===== 样本内网格扫描（找最优规则，样本≥300）=====")
    best = None
    for dt in [-0.05, -0.08, -0.10, -0.12, -0.15, -0.20]:
        for vr in [0.7, 0.8, 0.9, 1.0, 1.1, 1.2]:
            g = train[(train.deep20 < dt) & (train.vol_ratio > vr)]
            if len(g) >= 300:
                wr = np.mean(g.r10 > 0)
                if best is None or wr > best['wr']:
                    best = {'wr': wr, 'dt': dt, 'vr': vr, 'n': len(g), 'mean': np.mean(g.r10)}
    if best is None:
        print("⚠️ 样本内无满足样本≥300 的规则")
        return
    print(f"最优规则：深跌<{best['dt']:.0%} 且 放量>{best['vr']:.1f} —— 样本内 {best['n']}笔 10日胜率{best['wr']:.1%} 均值{best['mean']:+.2%}")

    # 样本外验证
    print("\n===== 样本外验证（防过拟合闸门）=====")
    m_test = (test.deep20 < best['dt']) & (test.vol_ratio > best['vr'])
    report("规则-样本内", train[(train.deep20 < best['dt']) & (train.vol_ratio > best['vr'])])
    report("规则-样本外", test[m_test])
    # 反向对照：深跌+缩量（验证"放量"方向是否样本外稳定）
    m_shrink = (test.deep20 < best['dt']) & (test.vol_ratio < 0.7)
    report("对照-样本外深跌+缩量", test[m_shrink])
    # 全样本
    m_all = (df.deep20 < best['dt']) & (df.vol_ratio > best['vr'])
    report("规则-全样本", df[m_all])


if __name__ == "__main__":
    main()
