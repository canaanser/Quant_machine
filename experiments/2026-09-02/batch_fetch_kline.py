# -*- coding: utf-8 -*-
"""
批量拉取 K 线缓存（2026-09-02 老板：8核8进程，只拉缺失，断点续拉）
=====================================================================
从本地 stockdb 拉 K 线 → data/cache/stockdb/{code}_1d.csv（自带 pe_ttm/pb/total_mv）
  一次搞定 K线 + 估值 + 市值（缓存列：date/close/high/low/volume/pe_ttm/pb/total_mv...）
用途：技术面筛选（深跌+放量）只要 K 线；王文五①估值 pe/pb 也够（②④⑤ 财报另需 online）

用法（Windows，8 核并行）：
    python -B scripts/batch_fetch_kline.py --codes 002987,002152,...     # 指定代码
    python -B scripts/batch_fetch_kline.py --list tickers_300.txt        # 从文件读
    python -B scripts/batch_fetch_kline.py --list tickers_300.txt --workers 8 --start 2021-01-01
特性：
  - 已有缓存且覆盖区间 → 跳过（不重复拉）
  - 断点续跑：中断后重跑只补缺失
  - 多进程并行（--workers，默认 8）
"""
import os
import sys
import time
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

START_DEFAULT = '2021-01-01'   # 训练期从 2021 起（技术面信号要够窗口）
END_DEFAULT = '2026-08-27'


def cache_ok(code: str, start: str, end: str) -> bool:
    """已有缓存且覆盖 start~end → True（跳过）"""
    p = ROOT / 'data' / 'cache' / 'stockdb' / f'{code}_1d.csv'
    if not (p.exists() and p.stat().st_size > 500):
        return False
    try:
        import pandas as pd
        df = pd.read_csv(p, encoding='utf-8', usecols=['date'])
        if df.empty:
            return False
        first = str(df['date'].iloc[0])[:10]
        last = str(df['date'].iloc[-1])[:10]
        return first <= start and last >= end
    except Exception:
        return False


def fetch_one(code: str, start: str, end: str) -> str:
    """拉单只 K 线（复用 core.data_loader 缓存机制）"""
    try:
        from core.data_loader import load_data
        md = load_data(source='freestockdb', tickers=[code], start=start,
                       end=end, frequency='1d', fq='qfq')
        if code in md.price.columns and len(md.price[code].dropna()) > 0:
            return 'ok'
        return 'empty'
    except Exception as e:
        return f'err:{str(e)[:40]}'


def worker(args):
    code, start, end = args
    if cache_ok(code, start, end):
        return code, 'cached'
    r = fetch_one(code, start, end)
    return code, r


def main():
    parser = argparse.ArgumentParser(description="批量拉K线缓存")
    parser.add_argument("--codes", default=None, help="逗号分隔代码")
    parser.add_argument("--list", default=None, help="代码列表文件（每行一个）")
    parser.add_argument("--workers", type=int, default=8, help="并行进程数")
    parser.add_argument("--start", default=START_DEFAULT)
    parser.add_argument("--end", default=END_DEFAULT)
    args = parser.parse_args()

    if args.codes:
        codes = [c.strip().zfill(6) for c in args.codes.split(',') if c.strip()]
    elif args.list:
        codes = [l.strip().zfill(6) for l in open(args.list, encoding='utf-8') if l.strip()]
    else:
        print("需 --codes 或 --list"); return
    # 去重
    seen = set()
    codes = [c for c in codes if not (c in seen or seen.add(c))]
    # 只留没拉过的
    todo = [c for c in codes if not cache_ok(c, args.start, args.end)]
    print(f"📦 共 {len(codes)} 只，已缓存跳过 {len(codes)-len(todo)}，待拉 {len(todo)}")

    if not todo:
        print("全部已有缓存，无需拉取"); return

    # 多进程并行（老板 8 核）
    try:
        from multiprocessing import Pool
        t0 = time.time()
        ok = cached = fail = 0
        with Pool(args.workers) as pool:
            for i, (code, r) in enumerate(pool.imap_unordered(
                    worker, [(c, args.start, args.end) for c in todo], chunksize=5)):
                if r == 'ok':
                    ok += 1
                elif r == 'cached':
                    cached += 1
                else:
                    fail += 1
                if (i + 1) % 25 == 0 or i == len(todo) - 1:
                    print(f"  进度 {i+1}/{len(todo)}  ok={ok} fail={fail}  "
                          f"耗时 {time.time()-t0:.0f}s", flush=True)
        print(f"\n完成: 成功 {ok}，失败 {fail}，跳过 {cached} | 总耗时 {time.time()-t0:.0f}s")
    except Exception as e:
        # Pool 不可用（如某些环境）→ 串行兜底
        print(f"⚠️ 多进程不可用({e})，改串行...")
        ok = fail = 0
        for code in todo:
            r = fetch_one(code, args.start, args.end)
            if r == 'ok':
                ok += 1
            else:
                fail += 1
        print(f"完成(串行): 成功 {ok}，失败 {fail}")


if __name__ == '__main__':
    main()
