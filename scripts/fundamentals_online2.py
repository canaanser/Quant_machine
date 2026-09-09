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
sys.path.insert(0, str(PROJECT_ROOT / '3rdpart_pybao'))
from config.config import SCAN_TICKERS, SCAN_TICKERS_CURATED, FUNDAMENTALS_REPORTS_DIR
import stock_sdk
import pandas as pd

OUT_DIR = PROJECT_ROOT / FUNDAMENTALS_REPORTS_DIR


def cache_ok(path) -> bool:
    """缓存校验：5 表全在才算有效（2026-08-30 防部分缓存挡路——上次失败的部分表缓存会跳过补拉）"""
    if not (path.exists() and path.stat().st_size > 500):
        return False
    try:
        df = pd.read_csv(path, encoding='utf-8')
        cols = list(df.columns)
        return all(t in cols for t in ('valuation', 'indicator', 'income', 'cash_flow', 'balance'))
    except Exception:
        return False


def market_suffix(code: str) -> str:
    """A股代码 → 带交易所后缀（深市XSHE/沪市XSHG；北交所暂按XSHE试）"""
    code = str(code).zfill(6)
    if code[0] in ('6', '9', '5'):
        return code + '.XSHG'
    return code + '.XSHE'


def fetch_stock_all_tables(suffix: str, quarters: list) -> dict:
    """逐票拉全部期 5 表（2026-09-02 老板：一只拿完再下一只，防批量限流全废）
    返回 {table: [rows...]}；任一期失败即整票作废（返回 None 由调用方跳过）
    表间 sleep 2s 限速——单票 5表×N期 请求稀疏，不触发批量限流"""
    import stock_sdk
    tables = ('valuation', 'indicator', 'income', 'cash_flow', 'balance')
    out = {}
    for tname in tables:
        tbl = getattr(stock_sdk, tname, None)
        if tbl is None:
            return None
        rows_all = []
        for p in quarters:
            got = False
            for attempt in range(3):
                try:
                    q = stock_sdk.query(tbl).filter(getattr(tbl, 'code') == suffix)
                    r = stock_sdk.get_fundamentals(q, statDate=p)
                    if isinstance(r, list):
                        rows_all.extend([dict(x) for x in r])
                        got = True
                        break
                    elif isinstance(r, str) and 'later' in str(r).lower():
                        time.sleep(5)  # 限流提示：等5s重试
                    else:
                        break
                except Exception:
                    time.sleep(2)
            if not got:
                return None  # 该期失败 → 整票不完整，放弃（宁缺毋滥）
        if rows_all:
            out[tname] = rows_all
        time.sleep(2)  # 表间限速
    return out if len(out) == len(tables) else None


def fetch_all_tables_batch(all_suffixes: list, quarters: list):
    """批量拉全池财务（2026-08-30 v4 按老板方案：表外层循环，表之间间隔 5 秒）
    每表：分批 in_(10只) × 4期；表间 sleep 5s；限流重试3次——全量 ~40 次查询不超限额"""
    tables = ('valuation', 'indicator', 'income', 'cash_flow', 'balance')
    per_code = {}
    BATCH, SLEEP = 10, 1.0
    for tname in tables:  # 表外层（老板：一只表拉完再下一只）
        tbl = getattr(stock_sdk, tname, None)
        if tbl is None:
            print(f"  ⚠️ 表 {tname} 不存在")
            continue
        print(f"  --- 拉 {tname} 表 ---")
        for bi in range(0, len(all_suffixes), BATCH):
            batch = all_suffixes[bi:bi + BATCH]
            for p in quarters:
                q = stock_sdk.query(tbl).filter(getattr(tbl, 'code').in_(batch))
                for attempt in range(3):
                    try:
                        r = stock_sdk.get_fundamentals(q, statDate=p)
                        if isinstance(r, list) and r:
                            df = pd.DataFrame(r)
                            for _, row in df.iterrows():
                                code = str(row.get('code', '')).zfill(6)
                                per_code.setdefault(code, {})
                                per_code[code].setdefault(tname, []).append(row.to_dict())
                            print(f"  ✅ {tname} {p} 批{bi//BATCH}: {len(df)} 条")
                            break
                        elif isinstance(r, str) and 'later' in r:
                            time.sleep(5)  # 限流：等5s重试
                            continue
                        else:
                            print(f"  ⚠️ {tname} {p} 批{bi//BATCH}: {str(r)[:80]}")
                            break
                    except Exception as e:
                        print(f"  ⚠️ {tname} {p} 批{bi//BATCH}: {str(e)[:80]}")
                        time.sleep(3)
                time.sleep(SLEEP)
        time.sleep(5)  # ← 老板：表之间间隔 5 秒
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
    # --quarters 自定义期数（2026-09-02 老板样本外实验：需拉 2022-2023 历史期判训练期）
    # 默认 4 期（够算同比，限流降负）；样本外实验建议 2023q3,2023q2,2023q1,2022q4,2022q3,2022q2,2022q1
    quarters = ['2024q4', '2024q3', '2024q2', '2024q1']
    if '--quarters' in sys.argv:
        quarters = [q.strip() for q in sys.argv[sys.argv.index('--quarters') + 1].split(',') if q.strip()]
        if not quarters:
            quarters = ['2023q3', '2023q2', '2023q1', '2022q4', '2022q3', '2022q2', '2022q1']
    # --codes 指定代码（2026-09-02 老板扩池：新票不在 84+15 池，需显式指定）
    custom_codes = []
    if '--codes' in sys.argv:
        custom_codes = [c.strip().zfill(6) for c in sys.argv[sys.argv.index('--codes') + 1].split(',') if c.strip()]
    pool = []
    seen = set()
    if custom_codes:
        pool = custom_codes
    else:
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
    # --per-stock 逐票完整拉（2026-09-02 老板：一只拿完再下一只，中途限流前面的也完整落盘）
    if '--per-stock' in sys.argv:
        ok = fail = 0
        for code in pool:
            cache = OUT_DIR / f"{code}.csv"
            if cache_ok(cache):
                ok += 1
                print(f"  ⏭️ {code}: 已有完整缓存")
                continue
            data = fetch_stock_all_tables(market_suffix(code), quarters)
            if not data:
                fail += 1
                print(f"  ❌ {code}: 拉取失败（可能限流，跳过继续下一只）")
                continue
            flat = {tname: json.dumps(rows, ensure_ascii=False, default=str) for tname, rows in data.items()}
            pd.DataFrame([{'code': code, 'suffix': market_suffix(code), **flat}]).to_csv(cache, index=False, encoding='utf-8')
            ok += 1
            print(f"  ✅ {code}: {len(quarters)}期×{len(data)}表 完整落盘")
        print(f"\n完成: 成功 {ok}，失败 {fail}")
        return
    for code in pool:
        cache = OUT_DIR / f"{code}.csv"
        if cache_ok(cache):  # 5表完整才命中；部分缓存作废重拉
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
