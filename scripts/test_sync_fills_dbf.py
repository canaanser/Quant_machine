#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""#2 回账 0 笔 的离线端到端验证（合成 execution_report.dbf，不碰真账本、不碰 C:\\emq）。

链路：duty_engine.task_close_sync → self_api.sync_fills() → FileOrderBroker.sync_fills()
      → _exec_report_rows() → read_dbf(<push_dir>/<account_id>/execution_report.dbf)

判据：2 条真回执（1 买 1 卖）必须被记进台账（打桩捕获），返回新增 2 笔。
      —— 字段错位时这里必然是 0（SID/SYMBOL/EXEC_TYPE 全解析坏）。
跑法：python -B scripts/test_sync_fills_dbf.py
"""
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.trade.file_order_broker import FileOrderBroker  # noqa: E402
from core.trade import ledger                            # noqa: E402

FIELDS = [("SID", "C", 22), ("SYMBOL", "C", 10), ("EXEC_TYPE", "N", 4),
          ("VOLUME", "N", 10), ("PRICE", "N", 12), ("ORDER_BIZ", "C", 2),
          ("CREATED_AT", "C", 22)]


def build_dbf(records) -> bytes:
    hlen = 32 + 32 * len(FIELDS) + 1
    rlen = 1 + sum(f[2] for f in FIELDS)
    head = bytearray(32)
    head[0] = 0x03
    head[4:8] = struct.pack("<I", len(records))
    head[8:10] = struct.pack("<H", hlen)
    head[10:12] = struct.pack("<H", rlen)
    desc = bytearray()
    for name, typ, ln in FIELDS:
        d = bytearray(32)
        d[0:len(name)] = name.encode("ascii")
        d[11] = ord(typ)
        d[16] = ln
        desc += d
    body = bytearray()
    for rec in records:
        body += b"\x20"                                   # 有效记录标志
        for name, typ, ln in FIELDS:
            v = str(rec.get(name, ""))
            raw = v.encode("gbk") if typ == "C" else v.encode("ascii")
            body += raw.rjust(ln) if typ == "N" else raw.ljust(ln)[:ln]
    return bytes(head) + bytes(desc) + b"\x0D" + bytes(body)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="syncfills-selftest-"))
    acct = "TESTACCT"
    (tmp / acct).mkdir()
    (tmp / acct / "execution_report.dbf").write_bytes(build_dbf([
        {"SID": "BUY20260911_093745.2841", "SYMBOL": "002428.SZ", "EXEC_TYPE": "15",
         "VOLUME": "100", "PRICE": "88.69", "ORDER_BIZ": "1", "CREATED_AT": "2026-09-11 09:36:03"},
        {"SID": "SELL20260911_144637.0001", "SYMBOL": "603256.SH", "EXEC_TYPE": "15",
         "VOLUME": "100", "PRICE": "129.26", "ORDER_BIZ": "2", "CREATED_AT": "2026-09-11 14:46:37"},
    ]))

    # 打桩：不读不写真台账
    ledger._load = lambda: {"positions": {}, "trades": [], "meta": {}}
    ledger._save = lambda *a, **k: None
    cap = []
    ledger.buy = lambda *a, **k: cap.append(("buy", a))
    ledger.sell = lambda *a, **k: cap.append(("sell", a))

    br = FileOrderBroker(push_dir=str(tmp), account_id=acct)
    n = br.sync_fills()
    print("sync_fills -> 新增 %d 笔；捕获 %s" % (n, cap))
    ok = (n == 2 and len(cap) == 2
          and cap[0][0] == "buy" and cap[0][1][0] == "002428"
          and cap[1][0] == "sell" and cap[1][1][0] == "603256")
    print("RESULT:", "PASS（#2 链路可入账）" if ok else "FAIL（仍 0 笔或解析错）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
