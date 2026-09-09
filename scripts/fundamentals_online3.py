# -*- coding: utf-8 -*-
"""在线财报拉取 v3 —— 王文五瘦身优化版（2026-09-06 老板：一次请求拉多点）

v2 的问题：每票 5表×4期 全拉、in_(10只) 小批 → 99 只也要 ~200 次请求，限额烧得冤。
王文五实际只读 indicator 表 1 列（ocf/毛利/净利/yoy 全在），①pe/pb 走本地 daily。

v3 优化：
1. 默认只拉 indicator 表（--all-tables 才拉 valuation/income/cash_flow/balance）
2. 默认最新 1 期（--quarters 可多期：indicator 的同比字段服务端已算好，王文五 1 期就够；
   样本外/历史回测才需多期）
3. 一批 in_(30只)（59437b3 证明 in_(全池99) 一次成功过；30 保守 + 可调 --batch）
4. 单票不完整不再整体作废：表级失败只记该票缺该表（王文五只要 indicator）

请求量估算（99 只，王文五模式）：indicator 1表 × 1期 × ceil(99/30)=4 批 ≈ 4 次
对比 v2：5表×4期×10批 ≈ 200 次 → 省 98%

用法（Windows）：python -B scripts/fundamentals_online3.py [--codes 列表] [--quarters 期数/列表]
                  [--all-tables] [--batch 30] [--per-stock] [--test 1]
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

TABLES = ('valuation', 'indicator', 'income', 'cash_flow', 'balance')
WW_TABLES = ('indicator',)  # 王文五只需 indicator（ocf_to_operating_profit / margins / yoy）


def market_suffix(code: str) -> str:
    code = str(code).zfill(6)
    return code + ('.XSHG' if code[0] in ('6', '9', '5') else '.XSHE')


def quarter_end(qstr: str) -> str:
    """statDate 季度串 '2026q2' → 截止日 '2026-06-30'"""
    y = int(qstr[:4]); q = int(qstr[4])
    return {1: f"{y}-03-31", 2: f"{y}-06-30", 3: f"{y}-09-30", 4: f"{y}-12-31"}[q]


def cache_ok(path, needed_quarters: list) -> bool:
    """缓存有效 = 文件含 indicator 且其最大 statDate ≥ 所需最新季度截止日
    （2026-09-06 修：老缓存只有 2024 年报却因"有 indicator 列"被跳过 → 永远补不上新鲜度）
    示例：要 2026q2(截止06-30)，缓存最大 statDate=2024-12-31 < 2026-06-30 → 需补拉"""
    if not (path.exists() and path.stat().st_size > 200):
        return False
    try:
        df = pd.read_csv(path, encoding='utf-8')
        if 'indicator' not in df.columns or pd.isna(df['indicator'].iloc[0]):
            return False
        ind = json.loads(df['indicator'].iloc[0])
        dates = [str(x.get('statDate', '')) for x in ind if x.get('statDate')]
        if not dates:
            return False
        latest = max(dates)  # 如 2024-12-31
        need = quarter_end(max(needed_quarters))  # 如 2026-06-30
        return latest >= need
    except Exception:
        return False


def recent_quarters(n: int = 1) -> list:
    """动态生成最近 N 个财报季 statDate —— 严格按披露节奏取"已披露"季度
    A股披露节奏：一季报4月底 / 中报8月底 / 三季报10月底 / 年报次年4月底
    → 9月初可用到 2026q2(中报)；10月底后才有 2026q3"""
    import datetime
    now = datetime.date.today()
    y, m = now.year, now.month
    if m <= 4:        # 1-4月：最新完整披露 = 上年 q3（年报/q4 次年4月底才出全）
        latest = (y - 1, 3)
    elif m <= 8:      # 5-8月：q1 已披露
        latest = (y, 1)
    elif m <= 10:     # 9-10月：中报 q2 已披露（q3 要 10月底）
        latest = (y, 2)
    else:             # 11-12月：q3 已披露
        latest = (y, 3)
    out = []
    yy, qq = latest
    for _ in range(n):
        out.append(f"{yy}q{qq}")
        qq -= 1
        if qq == 0:
            yy -= 1; qq = 4
    return out


def parse_args():
    # 默认：王文五监控只需最新 1 期（indicator 同比字段服务端算好，回测/样本外再 --quarters N）
    q = recent_quarters(1)
    tables = list(WW_TABLES)
    batch = 10  # v2 实证安全值（in_(24) 失败过，10 只/请求稳）
    per_stock = False
    codes = None
    test_n = 0
    argv = sys.argv
    if '--codes' in argv:
        codes = [c.strip().zfill(6) for c in argv[argv.index('--codes') + 1].split(',') if c.strip()]
    if '--quarters' in argv:
        raw = argv[argv.index('--quarters') + 1]
        if raw.isdigit():  # --quarters 4 → 最近 N 期
            q = recent_quarters(int(raw))
        else:
            q = [x.strip() for x in raw.split(',') if x.strip()]
    if '--all-tables' in argv:
        tables = list(TABLES)
    if '--batch' in argv:
        batch = int(argv[argv.index('--batch') + 1])
    if '--per-stock' in argv:
        per_stock = True
    if '--test' in argv:
        test_n = int(argv[argv.index('--test') + 1])
    return dict(q=q, tables=tables, batch=batch, per_stock=per_stock,
                codes=codes, test_n=test_n)


def fetch_batch(tname: str, suffixes: list, quarter: str, quiet_err=False):
    """一次 in_ 查询 N 只 1 期；返回 {code: dict} 或 None(失败)
    in_(24只) 失败过而 in_(1只) 成功 → 批量太大或偶发限流；失败自动缩小范围重试
    """
    tbl = getattr(stock_sdk, tname, None)
    if tbl is None:
        return None
    for attempt in range(4):
        try:
            q = stock_sdk.query(tbl).filter(getattr(tbl, 'code').in_(suffixes))
            r = stock_sdk.get_fundamentals(q, statDate=quarter)
            if isinstance(r, list) and r:
                out = {}
                for row in r:
                    d = dict(row)
                    # code 可能带后缀(000063.XSHE)或纯6位 → 统一去后缀取前6位数字
                    c = str(d.get('code', ''))
                    c = ''.join(ch for ch in c if ch.isdigit())[:6].zfill(6)
                    out[c] = d
                return out
            if isinstance(r, str) and ('later' in str(r).lower() or 'limit' in str(r).lower()):
                if not quiet_err:
                    print(f"      ⚠️ 限流提示(第{attempt+1}次): {str(r)[:100]}")
                time.sleep(5 * (attempt + 1))  # 等 5/10/15s 递增
                continue
            if not quiet_err:
                print(f"      ⚠️ 返回异常(第{attempt+1}次): {str(r)[:120]}")
            time.sleep(3)
        except Exception as e:
            if not quiet_err:
                print(f"      ⚠️ 异常(第{attempt+1}次): {str(e)[:120]}")
            time.sleep(3)
    return None


def fetch_with_halving(tname: str, suffixes: list, quarter: str, batch: int):
    """先整批试，失败则对半拆（应对单请求批量上限）：返回 {code: dict}"""
    out = {}
    queue = [suffixes]
    while queue:
        b = queue.pop(0)
        got = fetch_batch(tname, b, quarter, quiet_err=len(queue) > 20)
        if got is not None:
            out.update(got)
            continue
        if len(b) <= 1:  # 单只都失败 → 跳过
            print(f"  ❌ 单只仍失败: {b[0]}（真限流，等会再跑）")
            continue
        mid = len(b) // 2
        queue.extend([b[:mid], b[mid:]])
        print(f"  ↪ 拆半重试: {len(b)}只 → {mid}只 + {len(b)-mid}只")
    return out


def main():
    a = parse_args()
    try:
        stock_sdk.set_init("8.138.149.215:12328")
    except Exception as e:
        print(f"⚠️ set_init: {e}")
    os.makedirs(OUT_DIR, exist_ok=True)

    if a['codes']:
        pool = a['codes']
    else:
        pool = list(dict.fromkeys([str(c).zfill(6) for c in
                                   list(SCAN_TICKERS) + list(SCAN_TICKERS_CURATED)]))
    if a['test_n']:
        pool = pool[:a['test_n']]

    # 跳过已有缓存
    todo = [c for c in pool if not cache_ok(OUT_DIR / f"{c}.csv", a['q'])]
    skip = len(pool) - len(todo)
    print(f"📦 待拉 {len(todo)} 只（跳过缓存 {skip}）| 表: {a['tables']} | 期: {a['q']} | 批: {a['batch']}只/请求")
    if not todo:
        print("全部已有缓存 ✅")
        return

    suffixes = [market_suffix(c) for c in todo]
    # 预估请求次数
    est = sum(len(a['q']) * ((len(suffixes) + a['batch'] - 1) // a['batch']) for _ in a['tables'])
    print(f"🔢 预估请求: {est} 次（限额 2000/天）")

    per_code = {c: {} for c in todo}
    for tname in a['tables']:
        print(f"  --- {tname} ---")
        for p in a['q']:
            for bi in range(0, len(suffixes), a['batch']):
                b = suffixes[bi:bi + a['batch']]
                got = fetch_with_halving(tname, b, p, a['batch'])
                if got is None:
                    print(f"  ⚠️ {tname} {p} 批{bi//a['batch']} 失败（限流?）")
                    time.sleep(5)
                    continue
                for c in todo:
                    # fetch 返回 key = 纯6位 code（已规范化）
                    row = got.get(c)
                    if row is not None:
                        per_code[c].setdefault(tname, []).append(row)
                print(f"  ✅ {tname} {p} 批{bi//a['batch']}: {len(b)}只/请求 命中 {len(got)}")
                time.sleep(1.0)
            time.sleep(1.0)

    ok = fail = 0
    for code in todo:
        data = per_code.get(code)
        if not data or 'indicator' not in data:
            fail += 1
            print(f"  ❌ {code}: 无 indicator（限流或未披露）")
            continue
        # 增量合并：indicator 新旧期按 statDate 去重合并（老期保留，新期追加/覆盖）
        cache = OUT_DIR / f"{code}.csv"
        merged = dict(data)
        if cache.exists() and cache.stat().st_size > 200:
            try:
                old = pd.read_csv(cache, encoding='utf-8')
                for t in TABLES:
                    if t not in old.columns or pd.isna(old[t].iloc[0]):
                        continue
                    old_rows = json.loads(old[t].iloc[0])
                    if not old_rows:
                        continue
                    if t in merged:  # 本次拉到新期 → 合并去重
                        new_rows = merged[t]
                        seen = {str(r.get('statDate', r.get('id', ''))) for r in new_rows}
                        old_keep = [r for r in old_rows
                                    if str(r.get('statDate', r.get('id', ''))) not in seen]
                        merged[t] = old_keep + new_rows
                    else:           # 本次没拉该表 → 保留旧的
                        merged[t] = old_rows
            except Exception:
                pass
        # 只落盘本次涉及的 + 旧表保留：统一按 merged 写
        flat = {t: json.dumps(rows, ensure_ascii=False, default=str) for t, rows in merged.items()}
        pd.DataFrame([{'code': code, 'suffix': market_suffix(code), **flat}]).to_csv(
            cache, index=False, encoding='utf-8')
        ok += 1
        print(f"  ✅ {code}: {list(merged.keys())} ({len(merged.get('indicator', []))}期)")
    print(f"\n完成: 成功 {ok}，失败 {fail}（可重跑续拉，缓存命中跳过）")


if __name__ == '__main__':
    main()
