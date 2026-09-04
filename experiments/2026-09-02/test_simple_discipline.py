# -*- coding: utf-8 -*-
"""84只精选池 简单纪律打法雏形（2026-09-02 老板疯狂想法）
规则：赚 10% 卖 / 亏 5% 止损 / 逢低买（技术面深跌信号触发）
逢低买定义（参数化）：当日价 比 N 日前 跌 ≥ dip% 且放量 → 触发买入候选
对比：① 逢低+10%卖+5%止损 ② 纯金叉无止损（基线）
用法（Windows）：python -B scripts/test_simple_discipline.py
"""
import sys
import io
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

START, END = '2021-01-01', '2026-08-27'
TEST_START = '2025-01-01'


class DipBuyDiscipline:
    """逢低买入 + 固定止盈止损的简单纪律策略"""
    name = '逢低纪律'

    def __init__(self, dip_n=20, dip_pct=0.10, take_profit=0.10, stop_loss=0.05,
                 hold_limit=None, vol_boost=0.7):
        self.dip_n = dip_n
        self.dip_pct = dip_pct
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.hold_limit = hold_limit
        self.vol_boost = vol_boost
        self.window = dip_n + 1
        self.lookback = dip_n + 1

    def _dip_signal(self, price, volume=None):
        """逢低信号：比 dip_n 日前跌超 dip_pct%（可选放量确认），布尔序列"""
        ret = price / price.shift(self.dip_n) - 1
        sig = ret < -self.dip_pct
        if volume is not None:
            vr = volume / volume.shift(1).rolling(20).mean()
            sig = sig & (vr > self.vol_boost)
        return sig.fillna(False)

    def run(self, md, initial_cash=500000):
        """纯模拟：组合等权买入逢低信号票，10%卖/5%止损/持有上限60日"""
        px = md.price.copy()
        vol = md.volume.copy() if hasattr(md, 'volume') and md.volume is not None else None
        # 只看 2025 起（vol 同步切，否则索引错位信号全灭 2026-09-02 修复）
        px = px[px.index >= pd.Timestamp(TEST_START)]
        if vol is not None:
            vol = vol[vol.index >= pd.Timestamp(TEST_START)]
        cash = initial_cash
        positions = {}  # code -> {shares, cost, buy_date, idx}
        eq = []
        top_n = 10
        per_ticket = initial_cash / top_n  # 每票固定预算 5 万
        # 预计算每票 20日跌幅 + 放量比（向量化，避免逐日重算 O(n²)）
        dip_ret = px / px.shift(self.dip_n) - 1
        vol_ratio = None
        if vol is not None:
            vol_ratio = vol / vol.shift(1).rolling(20).mean()
        for i, (d, row) in enumerate(px.iterrows()):
            # 检查持仓：止盈/止损/超期
            for code in list(positions.keys()):
                p = positions[code]
                price = row.get(code)
                if pd.isna(price):
                    continue
                pnl = price / p['cost'] - 1
                # 老板规则：赚10%卖 / 亏5%止损（无持有期限硬顶——老板没要求 2026-09-02 修正）
                if pnl >= self.take_profit or pnl <= -self.stop_loss:
                    cash += p['shares'] * price
                    del positions[code]
            # 逢低信号 → 买入（最多 top_n 只，每票固定 per_ticket）
            if len(positions) < top_n:
                for code in px.columns:
                    if code in positions or i < self.dip_n:
                        continue
                    price = row.get(code)
                    if pd.isna(price) or price <= 0:
                        continue
                    if not (dip_ret[code].iloc[i] < -self.dip_pct):
                        continue
                    if vol_ratio is not None and code in vol_ratio.columns:
                        vr = vol_ratio[code].iloc[i]
                        if pd.notna(vr) and vr <= self.vol_boost:
                            continue  # 要放量确认
                    budget = min(cash, per_ticket)
                    shares = int(budget / price / 100) * 100
                    if shares >= 100:
                        cash -= shares * price
                        positions[code] = {'shares': shares, 'cost': price,
                                           'idx': i, 'buy_date': d}
            eq.append(cash + sum(p['shares'] * row.get(c, 0) for c, p in positions.items()
                                 if not pd.isna(row.get(c))))
        eq_s = pd.Series(eq, index=px.index)
        total = eq_s.iloc[-1] / initial_cash - 1
        dd = (eq_s / eq_s.cummax() - 1).min()
        return {'total': total, 'dd': dd, 'eq': eq_s}


def main():
    import logging as _logging
    _logging.disable(_logging.CRITICAL)
    from core.data_loader import load_data
    import config.config as cfg

    codes = list(cfg.SCAN_TICKERS)
    md = load_data(source='freestockdb', tickers=codes, start=START, end=END,
                   frequency='1d', fq='qfq')
    strat = DipBuyDiscipline()
    r = strat.run(md)
    print(f"84只 逢低纪律（跌10%买/盈10%卖/亏5%止损）:")
    print(f"  2025起收益 {r['total']:+.1%} | 最大回撤 {r['dd']:.1%}")


if __name__ == '__main__':
    main()
