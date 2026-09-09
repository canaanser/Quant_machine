# -*- coding: utf-8 -*-
"""DBF 文件读取(通用) — 东财/掘金回报 .dbf 解析
用法: from tools.toolkit.dbfread import read_dbf
"""
import struct


def read_dbf(path, max_rows=500):
    with open(path, "rb") as f:
        data = f.read()
    hlen = struct.unpack("<H", data[8:10])[0]
    rlen = struct.unpack("<H", data[10:12])[0]
    nrec = struct.unpack("<I", data[4:8])[0]
    fields = []
    pos = 32
    while data[pos] != 0x0D:
        name = data[pos:pos+11].split(b"\x00")[0].decode("ascii", "ignore")
        typ = chr(data[pos+11]); flen = data[pos+16]
        fields.append((name, typ, flen)); pos += 32
    rows = []
    p = hlen
    for _ in range(min(nrec, max_rows)):
        if data[p] == 0x2A:
            p += rlen; continue
        rec = {}
        for (name, typ, flen) in fields:
            val = data[p:p+flen]; p += flen
            if typ in "NF":
                try: val = float(val)
                except Exception: pass
            else:
                val = val.decode("gbk", "ignore").strip()
            rec[name] = val
        rows.append(rec)
    return fields, rows
