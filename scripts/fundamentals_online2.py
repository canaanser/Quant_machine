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


def fetch_tables(code_suffix: str, quarters: list, date_str: str = '2025-12-31'):
    """拉一只票各财务表（按季度 statDate 拉，合并）"""
    results = {}
    # 估值/指标表用 date（指定日前最新披露）；利润/现金流/资产负债表用 statDate（季度）
    table_cfgs = [
        ('valuation', 'date', None),
        ('indicator', 'date', None),
        ('income', 'statDate', quarters),
        ('cash_flow', 'statDate', quarters),
        ('balance', 'statDate', quarters),
    ]
    for tname, mode, qlist in table_cfgs:
        tbl = getattr(stock_sdk, tname, None)
        if tbl is None:
            print(f"  ⚠️ 表 {tname} 不存在")
            continue
        rows = []
        params = [date_str] if mode == 'date' else qlist
        for p in params:
            try:
                q = stock_sdk.query(tbl).filter(getattr(tbl, 'code') == code_suffix)
                kw = {mode: p}
                r = stock_sdk.get_fundamentals(q, **kw)
                if isinstance(r, list):  # 返回 list of dict（诊断确认）——转 DataFrame
                    rows.append(pd.DataFrame(r))
                elif hasattr(r, 'columns'):
                    rows.append(r)
                elif isinstance(r, str):
                    print(f"  ⚠️ {tname} {p}: {r[:100]}")
            except Exception as e:
                print(f"  ⚠️ {tname} {p}: {str(e)[:100]}")
            time.sleep(0.2)
        if rows:
            results[tname] = rows
    return results


def main():
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
    for i, code in enumerate(pool):
        suffix = market_suffix(code)
        cache = OUT_DIR / f"{code}.csv"
        if cache.exists() and cache.stat().st_size > 500:  # 新格式缓存（含5表JSON）才命中；旧api/json小缓存作废重拉
            ok += 1
            continue
        try:
            res = fetch_tables(suffix, quarters)
            if not res:
                fail += 1
                print(f"  ❌ {code}: 所有表失败")
                continue
            import pandas as pd
            # 合并各表 → 一行一表（宽表）
            flat = {}
            for tname, rows in res.items():
                try:
                    df = pd.concat(rows, ignore_index=True) if len(rows) > 1 else rows[0]
                    flat[tname] = df.to_json(orient='records', force_ascii=False)
                except Exception:
                    pass
            pd.DataFrame([{'code': code, 'suffix': suffix, **flat}]).to_csv(cache, index=False, encoding='utf-8')
            print(f"  ✅ {code}{suffix}: {list(res.keys())}")
            ok += 1
        except Exception as e:
            print(f"  ❌ {code}: {e}")
            fail += 1
    print(f"\n完成: 成功 {ok}，失败 {fail}")


if __name__ == '__main__':
    main()
