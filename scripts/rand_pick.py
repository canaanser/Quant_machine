# -*- coding: utf-8 -*-
"""
随机盲选股票生成器（2026-09-02 老板：盲选池测共性，不跟以前重复）
=================================================================
条件：① 沪深主板（排除科创 688/689、创业 300/301、北交所 8/4/9）
      ② 非 ST/*ST
      ③ 不与已有池重复（84主池 + 精选15 + 8只新扩池）
用法（Windows/WSL）：
    python -B scripts/rand_pick.py [--n 10] [--seed 42]
    # 生成的名单可直接喂 health_check：
    python -B scripts/health_check.py --tickers $(python -B scripts/rand_pick.py --n 10 --seed 42 --csv)
"""
import sys
import json
import random
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config.config as cfg

# 排除板块前缀
EXCLUDE_PREFIX = ('688', '689', '300', '301', '8', '4', '9')  # 科创/创业/北交所
# 沪深主板前缀（允许的）
MAIN_PREFIX = ('600', '601', '603', '605', '000', '001', '002', '003')


def load_existing() -> set:
    """已有池：84主池 + 精选15 + 8只新扩池（2026-09-02）"""
    existing = set(cfg.SCAN_TICKERS) | set(cfg.SCAN_TICKERS_CURATED)
    existing |= {'603019', '000977', '600160', '002050', '002837',
                 '001979', '000786', '002791'}  # 8只新扩池
    return {str(c).zfill(6) for c in existing}


def load_names():
    p = ROOT / 'data' / 'stock_names.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def main():
    parser = argparse.ArgumentParser(description="随机盲选股票")
    parser.add_argument("--n", type=int, default=10, help="选几只（默认10）")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（可复现）")
    parser.add_argument("--csv", action="store_true", help="只输出逗号分隔代码（管道给 health_check）")
    parser.add_argument("--list", default=str(ROOT / 'data' / 'stock_list.txt'),
                        help="股票列表文件（默认 data/stock_list.txt）")
    args = parser.parse_args()

    all_codes = [l.strip() for l in open(args.list, encoding='utf-8') if l.strip()]
    names = load_names()
    existing = load_existing()

    # 过滤：沪深主板 + 非已有 + 非ST
    pool = []
    for c in all_codes:
        c = c.zfill(6)
        if not c.startswith(MAIN_PREFIX):
            continue
        if c in existing:
            continue
        nm = str(names.get(c, ''))
        if 'ST' in nm.upper():
            continue
        pool.append(c)
    print(f"# 候选池: {len(pool)} 只（沪深主板，非ST，排除已有{len(existing)}只）", file=sys.stderr)

    if args.seed is not None:
        random.seed(args.seed)
    picked = random.sample(pool, min(args.n, len(pool)))

    if args.csv:
        print(','.join(picked))
    else:
        print(f"🎲 随机盲选 {len(picked)} 只（seed={args.seed}）:")
        for c in picked:
            print(f"  {c} {names.get(c, '?')}")


if __name__ == '__main__':
    main()
