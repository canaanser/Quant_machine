# -*- coding: utf-8 -*-
r"""东财量化终端 文件单 成交回读 → 自动记账 (2026-09-08)
终端输出目录结构: <out>/<account_id>/execution_report.csv position.csv cash.csv
读 execution_report.csv 里 exec_type=15(成交) 的回报, 去重后写入台账(core.trade.ledger),
卖出原因从备注/手动给, 默认 'emq文件单'。

用法(Windows cmd):
  E:\python\python.exe -B scripts\emq_pull.py --out C:\emq\push --account <账号ID> [--sell-reason 峰顶]
去重: 已处理过的 sid 记在 outputs/ledger.json 的 meta.seen_sids, 重复跑不重复记账
"""
import csv
import re
import sys
import time
from pathlib import Path
CFG = Path(__file__).parent.parent / "outputs" / "emq_config.json"
def _cfg():
    import json as _j
    try:
        return _j.load(open(CFG, encoding="utf-8"))
    except Exception:
        return {}


sys.path.insert(0, str(Path(__file__).parent.parent))
from core.trade.ledger import _load, _save


def col(headers, *keys):
    for h in headers:
        if any(k in h for k in keys):
            return h
    return None


def main():
    args = sys.argv[1:]
    def get(k, default=None):
        for i, a in enumerate(args):
            if a == k and i + 1 < len(args):
                return args[i + 1]
        return default
    out = get('--out')
    account = get('--account')
    reason = get('--sell-reason', 'emq文件单')
    c = _cfg()
    if not out:
        out = c.get('push_dir') or ''
    if not account:
        account = c.get('account_id') or ''
    if not out or not account:
        print(__doc__); return
    path = Path(out) / account / 'execution_report.csv'
    if not path.exists():
        print(f"找不到 {path} —— 检查: 终端文件单输出已启动? 输出目录/账号ID 对吗?"); return
    d = _load()
    seen = set(d.setdefault('meta', {}).setdefault('seen_sids', []))
    added = 0
    with open(path, encoding='utf-8-sig', errors='ignore') as f:
        rd = csv.reader(f)
        headers = next(rd, None)
        if not headers:
            print('空回报文件'); return
        c_sid = col(headers, 'sid'); c_sym = col(headers, 'symbol')
        c_vol = col(headers, 'volume'); c_px = col(headers, 'price')
        c_biz = col(headers, 'order_business'); c_type = col(headers, 'exec_type')
        c_time = col(headers, 'created_at'); c_amt = col(headers, 'amount')
        for row in rd:
            if len(row) < len(headers):
                continue
            rec = dict(zip(headers, row))
            if c_type and rec.get(c_type) != '15':
                continue
            sid = rec.get(c_sid) if c_sid else None
            if not sid or sid in seen:
                continue
            sym = rec.get(c_sym) or ''
            m = re.search(r'(\d{6})', sym)
            if not m:
                continue
            code = m.group(1)
            try:
                vol = int(float(rec[c_vol])); px = float(rec[c_px])
            except (TypeError, ValueError):
                continue
            biz = (rec.get(c_biz) or '').strip()
            date = (rec.get(c_time) or '')[:10].replace('-', '')
            if biz == '1':
                buy(code, date, vol, px, code)
            elif biz == '2':
                from core.trade.ledger import sell
                sell(code, date, px, reason)
            else:
                continue
            seen.add(sid)
            added += 1
            print(f"{'买入' if biz=='1' else '卖出'} {code} {vol}股 @{px} ({date}) sid={sid}")
    d['meta']['seen_sids'] = sorted(seen)
    _save(d)
    print(f"\n本次新增记账 {added} 笔 (去重总数 {len(seen)})")


if __name__ == '__main__':
    main()
