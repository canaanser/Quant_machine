# -*- coding: utf-8 -*-
"""
形态到底起不起作用？验证（2026-08-28 小二陈）

对比两组（同样 4 个状态条件：深跌>20% + 不显著放量 + 大实体 + 短下影）：
  A. 形态日版：只在"形态匹配日"上筛条件（当前信号，pattern_history 数据）
  B. 纯条件版：所有交易日直接筛条件（无形态识别）
若 A ≈ B → 形态冗余（信号纯状态驱动）；若 A > B → 形态识别在起作用。

口径（对齐原子公式）：
  深跌     dd = close/rolling120.max() - 1 < -0.20
  不显著放量 vol_ratio = 当日量/前5日均量 <= 1.4（对应 volume_spike <= 0.1）
  大实体   |close-open|/(high-low) >= 0.5
  短下影   (min(open,close)-low)/|close-open| <= 0.35

用法（Windows）：python scripts/verify_pattern_role.py [--pool main|ai]
"""
import sys, sqlite3, argparse
from pathlib import Path
import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

START, END = "2016-01-01", "2026-08-19"
HOLD = 5
DD = -0.20
VOL_RATIO = 1.4
BODY = 0.5
SHADOW = 0.35


def cond_B(ohlc):
    """纯条件版：逐日算条件，返回满足条件的未来5日收益列表"""
    close = ohlc['close'].astype(float)
    high = ohlc['high'].astype(float)
    low = ohlc['low'].astype(float)
    open_ = ohlc['open'].astype(float)
    vol = ohlc['volume'].astype(float)
    dd = close / close.rolling(120, min_periods=60).max() - 1
    avg5 = vol.rolling(5).mean().shift(1)            # 前5日均量（不含当日）
    vol_ratio = vol / avg5
    body = (close - open_).abs() / (high - low).replace(0, np.nan)
    lower_shadow = (np.minimum(open_, close) - low) / (close - open_).abs().replace(0, np.nan)
    fwd = close.shift(-HOLD) / close - 1
    mask = (dd < DD) & (vol_ratio <= VOL_RATIO) & (body >= BODY) & (lower_shadow <= SHADOW)
    return fwd[mask].dropna().tolist()


def cond_A(tickers):
    """形态日版：从 pattern_history 读形态日的状态条件"""
    conn = sqlite3.connect(f"file:{PROJECT / 'data/index_store/pattern_history.db'}?mode=ro", uri=True)
    atomic = {}
    for s, d, p, vs, br, sr in conn.execute(
            'SELECT symbol, date, pattern_id, volume_spike, body_ratio, shadow_ratio FROM atomic_features'):
        atomic[(s, p, d)] = (vs, br, sr)
    ph = "','".join(tickers)
    rets = []
    for s, p, dt, dd, r5 in conn.execute(
            f"SELECT symbol, pattern_id, substr(match_date,1,10), drawdown_from_peak, return_5d "
            f"FROM pattern_history WHERE symbol IN ('{ph}') AND return_5d IS NOT NULL"):
        a = atomic.get((s, p, dt))
        if a is None:
            continue
        vs, br, sr = a
        if (dd is not None and dd < DD and vs is not None and vs <= 0.1
                and br is not None and br >= BODY and sr is not None and sr <= SHADOW):
            rets.append(r5)
    conn.close()
    return rets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="main", choices=["main", "ai"])
    args = parser.parse_args()
    if args.pool == "ai":
        from config.config import SCAN_TICKERS_AI
        tickers = list(SCAN_TICKERS_AI)
    else:
        from config.config import SCAN_TICKERS
        tickers = list(SCAN_TICKERS)
    print(f"股票池: {len(tickers)} 只")

    from core.data_loader import load_data
    md = load_data(source='freestockdb', tickers=tickers, start=START, end=END, frequency='1d', fq='qfq')

    print("计算纯条件版（B，所有交易日）...")
    b_rets = []
    for sym in tickers:
        try:
            o = md.get_ohlc(sym)
            if o is not None and not o.empty and len(o) > 130:
                b_rets.extend(cond_B(o))
        except Exception:
            continue

    print("计算形态日版（A）...")
    a_rets = cond_A(tickers)

    def show(name, lst):
        if not lst:
            print(f"{name:<22} 无样本")
            return
        arr = np.array(lst)
        print(f"{name:<22} 样本={len(arr):>6} 胜率={np.mean(arr>0):>6.1%} 5日均={np.mean(arr):>+7.2%}")

    print()
    show("A. 形态日版", a_rets)
    show("B. 纯条件版(全交易日)", b_rets)
    if a_rets and b_rets:
        da = np.mean(np.array(a_rets) > 0)
        db = np.mean(np.array(b_rets) > 0)
        print(f"\n结论：形态日版胜率 {da:.1%} vs 纯条件版 {db:.1%}，差 {da-db:+.1%}")
        print("  |差|>3pt → 形态识别在起作用；≈0 → 形态冗余（信号纯状态驱动）")


if __name__ == "__main__":
    main()
