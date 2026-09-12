#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""回归测试：duty_engine.task_tail_exec 构造的卖出单必须是 dispatch 要的 5 元组。

背景（2026-09-11 事故）：卖单构造为 4 元组 `[code, shares, px, name]`，而
`self_api.dispatch()` 解包 5 元组 `(action, code, shares, px, name)` →
盘中 14:44 抛 `ValueError: not enough values to unpack (expected 5, got 4)`，当天买单也没发。

本测试不碰真单：把 `self_api._br` 换成桩，只验证"接口契约"。
跑法：python -B scripts/test_duty_tail_exec.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import self_api as api  # noqa: E402


class _StubBroker:
    def __init__(self):
        self.batches = []

    def place_batch(self, orders, make_fin=True):
        self.batches.append(list(orders))
        return ["sid%d" % i for i in range(len(orders))]


def _sells_from_source():
    """从真源里抠出两条 sells.append(...) 的行，确认都带 "SELL" 前缀且是 5 元组。"""
    src = (ROOT / "duty" / "duty_engine.py").read_text(encoding="utf-8")
    return [ln.strip() for ln in src.splitlines() if "sells.append(" in ln]


def main():
    ok = True

    # 1) 真源逐行检查：两条 append 都必须是 ["SELL", code, shares, px, name]
    appends = _sells_from_source()
    if len(appends) != 2:
        print("FAIL: 期望 2 处 sells.append，实际 %d" % len(appends))
        ok = False
    for ln in appends:
        if not re.search(r"sells\.append\(\[\s*[\"']SELL[\"']\s*,", ln):
            print("FAIL: 卖单未带 SELL 前缀 -> %s" % ln)
            ok = False

    # 2) 索引修正：去重判断必须看 s[1]（第 0 位现在是 "SELL"）
    src = (ROOT / "duty" / "duty_engine.py").read_text(encoding="utf-8")
    if "any(s[0] == code for s in sells)" in src:
        print("FAIL: 仍用 s[0] 做同码去重（s[0] 已是 \"SELL\"）")
        ok = False

    # 3) 接口契约：5 元组能过，4 元组必崩（复盘那次事故）
    stub = _StubBroker()
    api._br = stub
    rule = ["SELL", "603256", 100, 128.5, "宏和科技"]
    plan = ["SELL", "301358", 200, 53.4, "湖南裕能"]
    sids = api.dispatch([tuple(rule), tuple(plan)])
    if stub.batches and stub.batches[0] == [tuple(rule), tuple(plan)] and len(sids) == 2:
        print("PASS: 5 元组经 dispatch 正常落单（桩），sids=%s" % sids)
    else:
        print("FAIL: 5 元组未被正确透传 -> %r" % stub.batches)
        ok = False

    try:
        api.dispatch([("603256", 100, 128.5, "宏和科技")])  # 旧写法：4 元组
        print("FAIL: 4 元组竟然没崩（与 9/11 事故不符）")
        ok = False
    except ValueError as exc:
        print("PASS: 4 元组按预期抛 ValueError -> %s" % exc)

    print("RESULT:", "ALL PASS" if ok else "HAS FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
