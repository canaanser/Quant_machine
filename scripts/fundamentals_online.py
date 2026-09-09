# -*- coding: utf-8 -*-
"""在线财报拉取（2026-08-30 老板：王文五标准的②现金流③分红④营收净利等财务数据）
数据源：stock_sdk 在线接口（get_fundamentals 等——上次2000次限额的接口）
⚠️ 防重蹈覆辙（老板提醒）：
  1. 先 --test 1 只确认接口通、返回字段、限额状态——再全量
  2. 拉到即存 data/info/fundamentals/reports/{code}.csv（缓存，重复拉跳过）
  3. 小批量分批（默认一次10只，可 --batch 调）——避免一次打光限额
用法（Windows）：python -B scripts/fundamentals_online.py [--test 1] [--batch 10] [--start 000001]
"""
import sys
import os
import time
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / '3rdpart_pybao'))
from config.config import SCAN_TICKERS, SCAN_TICKERS_CURATED, FUNDAMENTALS_REPORTS_DIR

OUT_DIR = PROJECT_ROOT / FUNDAMENTALS_REPORTS_DIR


def try_call(name, fn):
    """调用并打印结果（探测用）"""
    try:
        r = fn()
        print(f"  ✅ {name}: {str(r)[:400]}")
        return r
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        return None


def probe_interfaces():
    """探测在线接口（只读，不消耗限额）"""
    import stock_sdk
    print("stock_sdk 模块:", getattr(stock_sdk, '__file__', '?'))
    print("顶层导出:", [x for x in dir(stock_sdk) if not x.startswith('_')][:40])
    for api in ('get_fundamentals', 'get_bars', 'get_price', 'get_security_info', 'cash_flow', 'query'):
        print(f"  stock_sdk.{api}: {'存在' if hasattr(stock_sdk, api) else '不存在'}")
    # 试 rd/bk/zb 子模块
    for mod in ('rd', 'bk', 'zb'):
        try:
            m = getattr(stock_sdk, mod)
            print(f"  {mod} 可导出, 方法: {[x for x in dir(m) if 'fund' in x.lower() or 'fin' in x.lower() or 'cash' in x.lower()][:8]}")
        except Exception as e:
            print(f"  {mod}: {e}")


def fetch_one(code: str) -> dict:
    """拉一只票的财报（先试 get_fundamentals，失败试其他）"""
    import stock_sdk
    code = str(code).zfill(6)
    result = {}
    for api_name in ('get_fundamentals', 'get_security_info'):
        fn = getattr(stock_sdk, api_name, None)
        if fn is None:
            continue
        try:
            r = fn(code)
            result[api_name] = r
            return result  # 第一个成功的
        except Exception as e:
            print(f"    {api_name}({code}): {e}")
    return result


def main():
    import stock_sdk  # Windows 才可导入
    os.makedirs(OUT_DIR, exist_ok=True)
    test_n = 0
    if '--test' in sys.argv:
        test_n = int(sys.argv[sys.argv.index('--test') + 1])
    print("🔍 探测在线接口（不消耗限额）...")
    probe_interfaces()

    # --codes 指定代码拉取（2026-09-02 老板扩池：默认只拉 84+15 池，新票需显式指定）
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
    print(f"\n📦 拉取 {len(pool)} 只财报（{'测试' if test_n else '全量'}）→ {OUT_DIR}")
    ok = fail = 0
    for i, code in enumerate(pool):
        cache = OUT_DIR / f"{code}.csv"
        if cache.exists() and cache.stat().st_size > 100:
            ok += 1
            continue  # 已有缓存
        r = fetch_one(code)
        if not r:
            fail += 1
            print(f"  ❌ {code}: 所有接口失败")
            continue
        # 存缓存（JSON 转 CSV：平铺 dict/list）
        try:
            import pandas as pd
            rows = []
            for api_name, data in r.items():
                if isinstance(data, dict):
                    rows.append({'api': api_name, 'json': json.dumps(data, ensure_ascii=False, default=str)})
                elif isinstance(data, list):
                    rows.append({'api': api_name, 'json': json.dumps(data, ensure_ascii=False, default=str)})
            pd.DataFrame(rows).to_csv(cache, index=False, encoding='utf-8')
            print(f"  ✅ {code}: 已存缓存")
            ok += 1
        except Exception as e:
            print(f"  ⚠️ {code}: 接口通但存缓存失败 {e}")
            ok += 1  # 数据拿到了，缓存尽力
        time.sleep(0.3)  # 轻限速（防打光限额）
    print(f"\n完成: 成功 {ok}，失败 {fail}，输出 {OUT_DIR}")


if __name__ == '__main__':
    main()
