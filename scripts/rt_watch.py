# -*- coding: utf-8 -*-
r"""盯盘器 scripts/rt_watch.py (模块化阶段1) — 盘中轮询持仓, 破防崩/峰顶就喊
用法(Windows cmd, 盘中开着):
  E:\python\python.exe -B scripts\rt_watch.py                    # 盯台账全部持仓
  E:\python\python.exe -B scripts\rt_watch.py --codes 603256,301358 --sec 10
  E:\python\python.exe -B scripts\rt_watch.py --once             # 只看一次(尾盘快照)
结合台账(ledger): 现价+防崩价/浮盈/峰顶状态一起打印; 破位行前加 [!!]
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.trade.rtfeed import fetch
from core.trade.ledger import status, _load

NAMES = {'603256': '宏和科技', '301358': '湖南裕能', '002595': '豪迈科技',
         '688775': '影石创新', '688702': '盛科通信-U', '688172': '燕东微'}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    sec = 30
    codes = None
    for a in sys.argv[1:]:
        if a.startswith('--sec='):
            sec = int(a[6:])
        elif a.startswith('--codes='):
            codes = [c for c in a[8:].split(',') if c]
    once = '--once' in sys.argv
    pos = _load()['positions']
    if not codes:
        codes = list(pos.keys())
    if not codes:
        print('台账空仓且未给 --codes'); return
    while True:
        px_map = {}
        for c, r in fetch(codes).items():
            px_map[c] = r['px']
        rows = status(px_map)
        ts = time.strftime('%H:%M:%S')
        print(f"\n--- {ts} 盯 {len(rows)} 仓 ---", flush=True)
        alert = False
        for r in rows:
            name = NAMES.get(r['code'], r.get('name', ''))
            if 'px' not in r:
                print(f"  {r['code']} {name} 无行情(可能停牌/代码错)"); continue
            act = r['action']
            flag = '[!!]' if act.startswith('⚠') else '  '
            if act.startswith('⚠'):
                alert = True
            print(f"{flag} {r['code']} {name:<8} 现价{r['px']:<9} 成本{r['cost']:.2f} "
                  f"盈亏{r['pnl_pct']:+.1f}% 防崩{r['fangbeng']:.2f} | {act}", flush=True)
        if alert:
            print("  !! 有破位/止盈信号, 按纪律处理 !!", flush=True)
        if once:
            return
        time.sleep(sec)


if __name__ == '__main__':
    main()
