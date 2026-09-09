# -*- coding: utf-8 -*-
"""实时取价统一 (tools/toolkit/quotes.py)
腾讯(盘中快, 主) + stockdb get_last_tick(收盘后/备) — final_order/rt_quotes/rt_stockdb 共用
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def tencent(codes):
    """腾讯批量实时价 → {code:{px,name,pct,high,low,open,ts}}"""
    from core.trade.rtfeed import fetch
    return fetch(codes)


def stockdb_last(codes, workers=8):
    """stockdb 网络端最新tick → {code: px} (并发)"""
    out = {}
    try:
        from concurrent.futures import ThreadPoolExecutor
        sys.path.insert(0, str(ROOT / "3rdpart_pybao"))
        import stockdb

        def one(c):
            try:
                r = stockdb.get_last_tick(c, count=1, df=False)
                if isinstance(r, list) and r:
                    return c, float(r[0]["current"])
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(one, codes):
                if r:
                    out[r[0]] = r[1]
    except Exception:
        pass
    return out


def live_px(codes, prefer="tencent"):
    """尾盘取价: 主腾讯; 腾讯缺的用 stockdb 补"""
    if prefer == "tencent":
        t = tencent(codes)
        px = {c: v["px"] for c, v in t.items()}
        missing = [c for c in codes if c not in px]
        if missing:
            px.update(stockdb_last(missing))
        return px
    else:
        px = stockdb_last(codes)
        missing = [c for c in codes if c not in px]
        if missing:
            t = tencent(missing)
            px.update({c: v["px"] for c, v in t.items()})
        return px
