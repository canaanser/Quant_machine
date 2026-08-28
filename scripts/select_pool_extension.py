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


def get_symbols(board_ref: str):
    """按板块代码精确查询成分（指南：bk.get('801150.SL') 返回含 symbols 的 dict），
    兼容 dict/list/嵌套结构，规整为代码列表"""
    res = bk.get(board_ref)
    syms = []
    if isinstance(res, dict):
        syms = res.get('symbols', [])
        if not syms:
            for v in res.values():
                if isinstance(v, list):
                    syms = v
                    break
    else:
        syms = res
    codes = []
    for s in syms:
        if isinstance(s, (list, tuple)):
            codes.extend(str(x) for x in s)
        else:
            codes.append(str(s))
    return codes


def pick(codes: list, per):
    """按申万一级板块代码拉成分，过滤后取 top N（市值排序尽力而为）"""
    names = load_names()
    board_names = {
        '801150.SL': '医药生物', '801740.SL': '国防军工', '801050.SL': '有色金属',
        '801020.SL': '采掘', '801780.SL': '银行', '801010.SL': '农林牧渔',
        '801030.SL': '化工', '801880.SL': '汽车', '801040.SL': '钢铁', '801110.SL': '家用电器',
    }
    chosen = []
    for bc in codes:
        ind = board_names.get(bc, bc)
        print(f"\n🚀 板块「{ind}」({bc}) 拉取成分 ...")
        try:
            symbols = get_symbols(bc)
        except Exception as e:
            print(f"  ❌ 拉取失败: {e}")
            continue
        if not symbols:
            print(f"  ⚠️ 空板块")
            continue
        cand = []
        for code in symbols:
            code = code.zfill(6) if code.isdigit() else code
            if code in EXISTING:
                continue
            nm = names.get(code, '')
            if 'ST' in nm.upper() or '退' in nm:
                continue
            cand.append(code)
        print(f"  成分 {len(symbols)} → 过滤后 {len(cand)}，取前 {per}")
        for code in cand[:per]:
            chosen.append((code, ind))
    print("\n===== 候选清单（80 只目标）=====")
    for code, ind in chosen:
        print(f"  {code} {names.get(code, '?'):<10} [{ind}]")
    print(f"\n共 {len(chosen)} 只")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="行业板块扩池选股")
    parser.add_argument("--list-industries", action="store_true", help="列出全部行业板块")
    parser.add_argument("--codes", default="", help="申万一级板块代码，逗号分隔（如 801150.SL,801740.SL）")
    parser.add_argument("--industries", default="", help="（旧）行业名，逗号分隔")
    parser.add_argument("--per", type=int, default=8, help="每板块选几只")
    args = parser.parse_args()

    if args.list_industries:
        list_industries()
    elif args.codes:
        pick([x.strip() for x in args.codes.split(',') if x.strip()], args.per)
    elif args.industries:
        print("⚠️ 中文板块名查询不稳，请用 --codes 传申万一级板块代码（如 801150.SL）")
    else:
        print("请指定 --list-industries 或 --codes")


if __name__ == "__main__":
    main()
