# -*- coding: utf-8 -*-
"""在线财报拉取（确定版，2026-08-30 按官方文档 https://a.123128.xyz/docs/）
表：indicator(指标)/income(利润)/cash_flow(现金流)/balance(资产负债表)/valuation(估值)
用法（文档）：
  get_fundamentals(query(indicator).filter(indicator.roe > 15), date='2024-12-31')
  get_fundamentals(query(income).filter(income.code == '000063.XSHE'), statDate='2024q4')
  get_fundamentals(query(cash_flow).filter(cash_flow.code == '000063.XSHE'), statDate='2024q4')
  get_fundamentals(query(balance).filter(balance.code == '000063.XSHE'), statDate='2024q4')
  get_fundamentals(query(valuation).filter(valuation.code == '000063.XSHE'), date='2025-12-31')
⚠️ 代码带交易所后缀：深市 .XSHE / 沪市 .XSHG
⚠️ 先 --test 1 确认字段 → 带缓存全量（不浪费限额）
用法（Windows）：python -B scripts/fundamentals_online2.py [--test 1] [--quarters 4]
"""
import sys
import json
import os
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'pybao'))
from config.config import SCAN_TICKERS, SCAN_TICKERS_CURATED
import stock_sdk
import pandas as pd

OUT_DIR = PROJECT_ROOT / 'data' / 'fundamentals_online'


def market_suffix(code: str) -> str:
    """A股代码 → 带交易所后缀（深市XSHE/沪市XSHG；北交所暂按XSHE试）"""
    code = str(code).zfill(6)
    if code[0] in ('6', '9', '5'):
        return code + '.XSHG'
    return code + '.XSHE'


def fetch_all_tables_batch(all_suffixes: list, quarters: list):
    """批量拉全池财务（2026-08-30 优化：filter(code.in_(全池)) 每表每期 1 次查询——总共 ~40 次调用，不超限额）
    返回 {code: {表名: DataFrame}}"""
    tables = ('valuation', 'indicator', 'income', 'cash_flow', 'balance')
    per_code = {}
    for tname in tables:
        tbl = getattr(stock_sdk, tname, None)
        if tbl is None:
            print(f"  ⚠️ 表 {tname} 不存在")
            continue
        for p in quarters:
            try:
                q = stock_sdk.query(tbl).filter(getattr(tbl, 'code').in_(all_suffixes))
                r = stock_sdk.get_fundamentals(q, statDate=p)
                if isinstance(r, list) and r:
                    df = pd.DataFrame(r)
                    for _, row in df.iterrows():
                        code = str(row.get('code', '')).zfill(6)
                        per_code.setdefault(code, {})
                        per_code[code].setdefault(tname, []).append(row.to_dict())
                    print(f"  ✅ {tname} {p}: {len(df)} 条")
                elif isinstance(r, str):
                    print(f"  ⚠️ {tname} {p}: {r[:100]}")
            except Exception as e:
                print(f"  ⚠️ {tname} {p}: {str(e)[:100]}")
            time.sleep(0.3)
    return per_code


def main():
    # 2026-08-30 配置在线API（官网start.html：set_init("8.138.149.215:12328")——在线财务/实时Tick接口）
    try:
        stock_sdk.set_init("8.138.149.215:12328")
        print("✅ 在线API已配置: 8.138.149.215:12328")
    except Exception as e:
        print(f"⚠️ set_init 失败: {e}")
    os.makedirs(OUT_DIR, exist_ok=True)
    test_n = 0
    if '--test' in sys.argv:
        test_n = int(sys.argv[sys.argv.index('--test') + 1])
    quarters = ['2024q4', '2024q3', '2024q2', '2024q1', '2023q4', '2023q3', '2023q2', '2023q1']
    pool = []
    seen = set()
    for c in list(SCAN_TICKERS) + list(SCAN_TICKERS_CURATED):
        c = str(c).zfill(6)
        if c not in seen:
            seen.add(c)
            pool.append(c)
    if test_n:
        pool = pool[:test_n]
    print(f"📦 拉取 {len(pool)} 只财务（{'测试' if test_n else '全量'}）→ {OUT_DIR}")
    print(f"   季度: {quarters[:4]}... 表: valuation/indicator/income/cash_flow/balance")
    ok = fail = 0
    # 批量：filter(code.in_(全池)) 每表每期 1 次查询（~40 次调用，不超限额）
    all_suffixes = [market_suffix(c) for c in pool]
    per_code = fetch_all_tables_batch(all_suffixes, quarters)
    for code in pool:
        cache = OUT_DIR / f"{code}.csv"
        if cache.exists() and cache.stat().st_size > 500:
            ok += 1
            continue
        data = per_code.get(code)
        if not data:
            fail += 1
            print(f"  ❌ {code}: 无数据")
            continue
        flat = {tname: json.dumps(rows, ensure_ascii=False, default=str) for tname, rows in data.items()}
        pd.DataFrame([{'code': code, 'suffix': market_suffix(code), **flat}]).to_csv(cache, index=False, encoding='utf-8')
        ok += 1
        print(f"  ✅ {code}: {list(data.keys())}")
    print(f"\n完成: 成功 {ok}，失败 {fail}")


if __name__ == '__main__':
    main()
