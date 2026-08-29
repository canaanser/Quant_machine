"""从 stockdb 拉取股票池基本面数据（2026-08-30 老板：王文五标准基本面精选的数据基础）
数据源：free-stockdb 本地 HTTP 服务（127.0.0.1:7899）——本地接口，不烧在线限额
字段：pe_ttm（市盈率TTM）/ pb（市净率）/ total_mv（总市值）/ float_mv（流通市值）
     / total_share（总股本）/ float_share（流通股本）/ is_st（ST标记）
存储：data/fundamentals/{code}.csv（拉到就存，重复拉直接读缓存——不浪费）
用法：python fundamentals_fetch.py [--test 5]  # --test 只拉前N只验证
"""
import os
import sys
import json
import time
import urllib.request
import urllib.parse
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from config.config import SCAN_TICKERS, SCAN_TICKERS_CURATED  # 84只主池 + 精选15只

HOST = "127.0.0.1"
PORT = 7899
FIELDS = ['pe_ttm', 'pb', 'total_mv', 'float_mv', 'total_share', 'float_share', 'is_st']
OUT_DIR = os.path.join(ROOT, 'data', 'fundamentals')


def fetch_kline(code: str, year: int) -> list:
    """HTTP 拉一年日K（含基本面字段）"""
    expr = f"日k:{code}:{year}*"
    url = f"http://{HOST}:{PORT}/?cmd=get&t={urllib.parse.quote(expr)}"
    with urllib.request.urlopen(url, timeout=30) as r:
        raw = json.loads(r.read().decode('utf-8'))
    rows = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) > 1 and isinstance(item[1], dict):
            rows.append(item[1])
    return rows


def fetch_stock_fundamentals(code: str, start_year: int = 2020) -> pd.DataFrame:
    """拉一只票多年度基本面，合并去重，返回 DataFrame"""
    code = str(code).zfill(6)
    frames = []
    end_year = 2026
    for year in range(start_year, end_year + 1):
        try:
            rows = fetch_kline(code, year)
            if rows:
                frames.append(pd.DataFrame(rows))
            time.sleep(0.05)  # 轻限速，不压垮本地服务
        except Exception as e:
            print(f"  ⚠️ {code} {year} 失败: {e}")
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=['date', 'code'], keep='last')
    df['date'] = pd.to_datetime(df['date'].astype(str), format='%Y%m%d', errors='coerce')
    df = df.dropna(subset=['date']).sort_values('date')
    return df


def main():
    test_n = 0
    if '--test' in sys.argv:
        test_n = int(sys.argv[sys.argv.index('--test') + 1])
    os.makedirs(OUT_DIR, exist_ok=True)
    # 池：84主池 + 精选15（去重）
    pool = []
    seen = set()
    for c in list(SCAN_TICKERS) + list(SCAN_TICKERS_CURATED):
        c = str(c).zfill(6)
        if c not in seen:
            seen.add(c)
            pool.append(c)
    if test_n > 0:
        pool = pool[:test_n]
    print(f"📦 拉取 {len(pool)} 只基本面（{'测试模式前'+str(test_n) if test_n else '全量'}）→ {OUT_DIR}")
    ok, fail = 0, 0
    for i, code in enumerate(pool):
        cache = os.path.join(OUT_DIR, f"{code}.csv")
        if os.path.exists(cache) and os.path.getsize(cache) > 100:
            ok += 1
            continue  # 已有缓存，跳过（不重复拉）
        try:
            df = fetch_stock_fundamentals(code)
            if df.empty:
                print(f"  ⚠️ {code}: 无数据")
                fail += 1
                continue
            # 只留基本面相关列（date + 基本面 + 收盘价参考）
            keep = [c for c in ['date', 'close'] + FIELDS if c in df.columns]
            df[keep].to_csv(cache, index=False, encoding='utf-8')
            ok += 1
            print(f"  ✅ {code}: {len(df)} 天 → {os.path.basename(cache)}")
        except Exception as e:
            print(f"  ❌ {code}: {e}")
            fail += 1
    print(f"\n完成: 成功 {ok}，失败 {fail}，输出 {OUT_DIR}")


if __name__ == '__main__':
    main()
