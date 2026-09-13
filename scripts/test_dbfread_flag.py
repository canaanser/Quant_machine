#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""合成 DBF 回归测试：验证 read_dbf 会**消费记录头那 1 个标志字节**。

背景（2026-09-11 账目失真疑因）：DBF 的 record length（头 10-11 字节）**含**每记录的
1 字节删除标志；旧实现跳过删除记录，但读取正常记录时**没把标志字节算进去**，
于是每个字段整体错位 1 字节 —— 现场表现就是"解析器字段错位"。

本测试自带一份最小 DBF（2 字段 / 3 记录，其中 1 条是删除记录），不依赖任何外部数据。
跑法：python -B scripts/test_dbfread_flag.py
"""
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.lib.dbfread import read_dbf  # noqa: E402


def build_dbf() -> bytes:
    fields = [("CODE", "C", 6), ("NAME", "C", 12)]
    hlen = 32 + 32 * len(fields) + 1
    rlen = 1 + sum(f[2] for f in fields)          # ★ 含 1 字节标志
    head = bytearray(32)
    head[0] = 0x03
    head[1], head[2], head[3] = 26, 9, 14
    head[4:8] = struct.pack("<I", 3)              # 记录数
    head[8:10] = struct.pack("<H", hlen)
    head[10:12] = struct.pack("<H", rlen)
    desc = bytearray()
    for name, typ, ln in fields:
        d = bytearray(32)
        d[0:len(name)] = name.encode("ascii")
        d[11] = ord(typ)
        d[16] = ln
        desc += d
    body = bytearray()
    body += b"\x20" + "603256".encode("ascii").ljust(6) + "宏和科技".encode("gbk").ljust(12)
    body += b"\x2A" + b"999999" + "已删除记录".encode("gbk").ljust(12)   # 删除记录
    body += b"\x20" + "301358".encode("ascii").ljust(6) + "湖南裕能".encode("gbk").ljust(12)
    return bytes(head) + bytes(desc) + b"\x0D" + bytes(body)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="dbfread-selftest-")) / "t.dbf"
    tmp.write_bytes(build_dbf())
    fields, rows = read_dbf(str(tmp), max_rows=10)
    print("fields = %s" % [(f[0], f[1], f[2]) for f in fields])
    print("rows   = %s" % [(r.get("CODE", ""), r.get("NAME", "")) for r in rows])

    ok = True
    if len(rows) != 2:
        print("FAIL: 期望 2 条（删除记录被跳过），实得 %d" % len(rows))
        ok = False
    codes = [str(r.get("CODE", "")).strip() for r in rows]
    if codes != ["603256", "301358"]:
        print("FAIL: CODE 字段错位 -> %s（应为 ['603256','301358']）" % codes)
        ok = False
    names = [str(r.get("NAME", "")).strip() for r in rows]
    if names != ["宏和科技", "湖南裕能"]:
        print("FAIL: NAME 字段错位 -> %s" % names)
        ok = False
    print("RESULT:", "PASS（字段对齐、删除记录已跳过）" if ok else "MISALIGN（字段错位）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
