# -*- coding: utf-8 -*-
"""
按行业板块扩池选股（第一阶段：列行业板块 → 第二阶段：选 80 只）
=====================================================================
2026-08-28 小二陈（老板思路：SDK 板块接口 bk.get 直接按行业选股）：
  扩池 80 只（84 主池 → 164），行业分散（补医药/军工/新能源/周期/金融等盲区）。
  用法（Windows，需 stockdb 服务）：
    1) python -B scripts/select_pool_extension.py --list-industries
       → 打印全部行业板块（含股票数），老板选定目标行业
    2) python -B scripts/select_pool_extension.py --industries 医药,军工,新能源 --per 10
       → 每行业按市值选 top N，输出候选清单（排除已有池与 ST）
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / 'pybao') not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / 'pybao'))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import stock_sdk  # noqa: E402  （pybao/stock_sdk.py，bk 是其 lazy 板块导出）
bk = stock_sdk.bk
import config.config as config_mod  # noqa: E402

# 已有池（排除）
EXISTING = set(config_mod.SCAN_TICKERS) | set(getattr(config_mod, 'SCAN_TICKERS_AI', []))


def load_names():
    p = PROJECT_ROOT / 'data' / 'stock_names.json'
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return {}


def list_industries():
    """列出全部行业板块"""
    print("🚀 拉取行业板块列表 ...")
    boards = bk.get(category=1, fields="name,code")
    print(f"返回类型: {type(boards)}")
    if isinstance(boards, dict):
        items = list(boards.items())[:5]
        print(f"dict 样例: {items}")
        return
    # 尝试各种结构
    if isinstance(boards, (list, tuple)):
        print(f"list 长度: {len(boards)}")
        for b in boards[:30]:
            print(f"  {b}")
        return
    print(f"原始: {str(boards)[:500]}")


def get_float_mv(code: str):
    """尽力拉流通市值（float_mv），失败返回 None（排最后）"""
    try:
        import stock_sdk
        client = stock_sdk.get_default_client()
        rec = client.get_data(code, fields="float_mv")
        if isinstance(rec, dict):
            v = rec.get('float_mv') or rec.get('0')
        else:
            v = rec
        return float(v) if v else None
    except Exception:
        return None


def pick(industries, per):
    """按行业拉成分，过滤后按市值排序选 top N"""
    names = load_names()
    chosen = []
    for ind in industries:
        print(f"\n🚀 行业「{ind}」拉取成分 ...")
        try:
            symbols = bk.get(ind, 0, "symbols")
        except Exception as e:
            print(f"  ❌ 拉取失败: {e}")
            continue
        if isinstance(symbols, dict):
            symbols = symbols.get('symbols', symbols)
        if not symbols:
            print(f"  ⚠️ 空板块")
            continue
        # 过滤已有池 + ST
        cand = []
        for code in symbols:
            code = str(code).zfill(6) if str(code).isdigit() else str(code)
            if code in EXISTING:
                continue
            nm = names.get(code, '')
            if 'ST' in nm.upper() or '退' in nm:
                continue
            cand.append(code)
        print(f"  成分 {len(symbols)} → 过滤后 {len(cand)}，拉市值排序 ...")
        # 市值排序（尽力而为）
        ranked = []
        for code in cand:
            mv = get_float_mv(code)
            ranked.append((code, mv))
        ranked.sort(key=lambda x: -(x[1] if x[1] is not None else -1))
        if not any(mv is not None for _, mv in ranked):
            print("  ⚠️ 市值拉取失败，按板块顺序取")
        for code, mv in ranked[:per]:
            chosen.append((code, ind, mv))
    print("\n===== 候选清单 =====")
    for code, ind, mv in chosen:
        mv_s = f"{mv/1e8:.0f}亿" if mv else "?"
        print(f"  {code} {names.get(code, '?'):<10} [{ind}] {mv_s}")
    print(f"\n共 {len(chosen)} 只（目标 {len(industries) * per}）")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="行业板块扩池选股")
    parser.add_argument("--list-industries", action="store_true", help="列出全部行业板块")
    parser.add_argument("--industries", default="", help="目标行业，逗号分隔")
    parser.add_argument("--per", type=int, default=10, help="每行业选几只")
    args = parser.parse_args()

    if args.list_industries:
        list_industries()
    elif args.industries:
        pick([x.strip() for x in args.industries.split(',') if x.strip()], args.per)
    else:
        print("请指定 --list-industries 或 --industries")


if __name__ == "__main__":
    main()
