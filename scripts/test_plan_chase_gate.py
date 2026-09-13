#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""买入侧"追高闸"回归测试（老板 2026-09-14 交办：把"人肉删行"固化成引擎判据）。

覆盖两件：
  ① `_read_plan()` 能读第 6 列 `max_px`（缺省空 = 不设闸），且**老的 5 列文件行为不变**；
  ② `_chase_blocked()`（引擎里真正用的那个判据）在 实时价 > 上限 时拦住、否则放行。
跑法：python -B scripts/test_plan_chase_gate.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import duty.duty_engine as de  # noqa: E402


def _with_plan(text):
    tmp = Path(tempfile.mkdtemp(prefix="plan-gate-selftest-"))
    (tmp / "outputs").mkdir()
    (tmp / "outputs" / "next_plan.csv").write_text(text, encoding="utf-8")
    de.ROOT = tmp                      # 只改这一个模块的根，指向临时目录
    return de._read_plan()


def main():
    ok = True

    # ① 六列：带追高上限
    plan = _with_plan("code,side,shares,price,name,max_px\n"
                      "688775,buy,100,94.47,影石创新,105.25\n"
                      "603256,sell,100,129.80,宏和科技,\n")
    print("六列解析 -> %s" % plan)
    if plan[0][5] != 105.25 or plan[1][5] is not None:
        print("FAIL: max_px 解析不对")
        ok = False

    # ② 老文件（5 列）行为不变：max_px = None
    plan5 = _with_plan("code,side,shares,price,name\n688775,buy,100,94.47,影石创新\n")
    print("五列解析 -> %s" % plan5)
    if plan5[0][5] is not None:
        print("FAIL: 老文件应无闸（max_px=None）")
        ok = False

    # ③ 闸本体
    cases = [((100.0, 105.25), False, "低于上限→放行"),
             ((105.26, 105.25), True, "高于上限→拦住"),
             ((105.25, 105.25), False, "等于上限→放行"),
             ((100.0, None), False, "没设上限→放行")]
    for (px, mx), want, why in cases:
        got = de._chase_blocked(px, mx)
        if got != want:
            print("FAIL: %s（px=%s mx=%s 得 %s）" % (why, px, mx, got))
            ok = False
    print("闸判据 4 例 -> %s" % ("OK" if ok else "有失败"))

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
