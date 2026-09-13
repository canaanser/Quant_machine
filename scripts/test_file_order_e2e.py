#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""端到端：让**引擎自己的** `task_tail_exec()` 真写一次文件单（写到临时目录，不碰 C:\\emq）。

验收目标（老板 2026-09-14 06:0x 交办）：**只要能写出文件单就算通**——
即 `<scan_dir>/<ts>.order.csv` + `.fin` 落地，内容和东财终端的列口径一致。

三个场景：
  ① 正常：卖 603256 100 + 买 688775 100 → 一个文件单、两行；
  ② 追高闸：同一买单把实时价抬到上限之上 → **只剩卖单一行**，且写了"跳过买入"决策；
  ③ 文件格式：表头 8 列、SELL→order_biz=2、BUY→order_biz=1、价格保留 2 位。
跑法：python -B scripts/test_file_order_e2e.py
"""
import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import duty.duty_engine as de                          # noqa: E402
from core.trade.file_order_broker import FileOrderBroker  # noqa: E402

PLAN = [("603256", "sell", 100, "129.80", "宏和科技", None),
        ("688775", "buy", 100, "94.47", "影石创新", 105.25)]


def run_once(px_map):
    """跑一次引擎执行段，返回 (scan_dir, 决策列表)"""
    tmp = Path(tempfile.mkdtemp(prefix="fileorder-e2e-"))
    scan, push = tmp / "scan", tmp / "push"
    br = FileOrderBroker(scan_dir=str(scan), push_dir=str(push), account_id="TESTACCT")
    decisions = []

    class ApiStub:
        @staticmethod
        def positions():
            return {"603256": {"shares": 400}}

        @staticmethod
        def evaluate_holdings(px):
            return []                                  # 不加规则卖，只看计划

        @staticmethod
        def dispatch(actions):
            return br.place_batch([tuple(a) for a in actions])

    de.SHADOW = False
    de.api = ApiStub()
    de._read_plan = lambda: list(PLAN)
    de._px_retry = lambda codes: dict(px_map)
    de._already_sent = lambda: False
    de._mark_sent = lambda rows: None
    de.decision = lambda s: decisions.append(s)
    de.log = lambda s: None
    de.task_tail_exec()
    return scan, decisions


def orders_in(scan_dir):
    files = sorted(scan_dir.glob("*.order.csv"))
    rows = []
    if files:
        with open(files[0], encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
    return files, rows


def all_rows(scan_dir):
    """把该目录下所有文件单的数据行合起来（引擎是**卖、买各写一个文件**）。"""
    out, hdr = [], None
    for f in sorted(scan_dir.glob("*.order.csv")):
        with open(f, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        if rows:
            hdr = hdr or rows[0]
            out.extend(rows[1:])
    return hdr, out


def main():
    ok = True

    # ① 正常路径：引擎把**卖、买各写一个文件单**（共 2 个文件、2 行数据）+ 各自 .fin
    scan1, dec1 = run_once({"603256": 129.50, "688775": 94.00})
    files1, _ = orders_in(scan1)
    hdr1, rows1 = all_rows(scan1)
    print("① 文件单 = %s" % [f.name for f in files1])
    print("① 内容 = %s" % rows1)
    if len(files1) != 2 or len(rows1) != 2:
        print("FAIL: 期望 2 个文件单（卖/买各一）、2 行数据")
        ok = False
    if not all(Path(str(f) + ".fin").exists() for f in files1):
        print("FAIL: 有文件单缺 .fin")
        ok = False
    if hdr1 != ["sid", "account_id", "symbol", "volume", "order_type",
                "order_business(order_biz)", "price", "comment"]:
        print("FAIL: 表头不对 -> %s" % hdr1)
        ok = False
    biz = sorted(r[5] for r in rows1)
    if biz != ["1", "2"]:
        print("FAIL: 买卖方向编码不对（应 SELL=2 / BUY=1）-> %s" % biz)
        ok = False
    pxes = sorted(r[6] for r in rows1)
    if pxes != ["129.5", "94.0"]:
        print("FAIL: 价格格式不对 -> %s" % pxes)
        ok = False

    # ② 追高闸：实时 106.00 > 上限 105.25 → 只剩卖单
    scan2, dec2 = run_once({"603256": 129.50, "688775": 106.00})
    files2, _ = orders_in(scan2)
    _, rows2 = all_rows(scan2)
    print("② 追高时文件单 = %s / 内容 = %s" % ([f.name for f in files2], rows2))
    print("② 决策 = %s" % [d for d in dec2 if "跳过买入" in d])
    if len(rows2) != 1 or rows2[0][5] != "2":
        print("FAIL: 追高时应只剩卖单 1 行")
        ok = False
    if not any("跳过买入" in d for d in dec2):
        print("FAIL: 未写'跳过买入'决策")
        ok = False

    print("RESULT:", "PASS（引擎能写出文件单，且追高闸生效）" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
