# -*- coding: utf-8 -*-
"""探测 stockdb 按名称查询能力（2026-08-28 小二陈）
1) 试 LevelDB 是否有名称索引键（"名称*"/"name*"）→ 可直接按名搜
2) 否则：批量 get_data(fields=name) 导出 {code: name} 到 data/stock_names.json
用法（Windows）：python scripts/probe_names.py
"""
import sys, json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "pybao"))


def main():
    from stock_sdk import get_default_client
    client = get_default_client()

    # 1. 试名称索引键
    print("=== 1. 试 LevelDB 名称键 ===")
    found = False
    for p in ['名称', 'name', 'NAME', '股票名']:
        try:
            raw = client.rd.get(f'{p}*') if hasattr(client, 'rd') else None
            if raw is None:
                raw = client.rd.get(f'{p}*') if hasattr(client.rd, 'get') else None
            if raw:
                items = raw.get('cum', raw) if isinstance(raw, dict) else raw
                n = len(items) if items else 0
                print(f'  {p}*: {n} 条, 样例={items[0] if items else None}')
                if n:
                    found = True
            else:
                print(f'  {p}*: 0 条')
        except Exception as e:
            print(f'  {p}*: 失败 {type(e).__name__}: {str(e)[:50]}')

    # 2. 批量导出 {code: name}
    print("\n=== 2. 批量取名称（5821 只，fields=name）===")
    lst = PROJECT / "data" / "stock_list.txt"
    if not lst.exists():
        print("  无 stock_list.txt，先跑 scripts/dump_stock_list.py")
        return
    codes = [l.strip() for l in lst.read_text(encoding='utf-8').splitlines() if l.strip()]
    print(f"  股票数: {len(codes)}")

    names = {}
    BATCH = 500
    try:
        for i in range(0, len(codes), BATCH):
            batch = codes[i:i + BATCH]
            res = client.get_data(batch, limit=1, desc=True, fields='code,name', as_df=False)
            if isinstance(res, dict):
                for c, recs in res.items():
                    if recs:
                        r = recs[0]
                        nm = r.get('name') if isinstance(r, dict) else (r[-1] if isinstance(r, (list, tuple)) else None)
                        names[c] = str(nm) if nm else ''
            print(f"  批 {i // BATCH + 1}: 累计 {len(names)} 个名称")
    except Exception as e:
        print(f"  批量失败（部分完成 {len(names)} 个）: {type(e).__name__}: {str(e)[:80]}")

    if names:
        out = PROJECT / "data" / "stock_names.json"
        out.write_text(json.dumps(names, ensure_ascii=False, indent=0), encoding='utf-8')
        print(f"  名称清单: {len(names)} 条 → {out}")
        # 样例
        for c in list(names)[:5]:
            print(f"    {c}: {names[c]}")
    else:
        print("  未取到任何名称")


if __name__ == "__main__":
    main()
