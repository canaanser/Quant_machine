#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""到点唤醒 DSH 的离线自测（口径：**提前 10 秒、只响一次**）：不真发门铃，只验判据。

验六件：
  ① 不到 -10 秒不叫（09:29:45 不响）
  ② 到 -10 秒叫一次（09:29:50 响）；同一天不重复
  ③ 过点超 grace → 不补叫
  ④ 18:30 也能叫（周期任务，不吃引擎"16:00 后不补跑"那条规则）
  ⑤ 周末一次都不叫
  ⑥ 跨日自动重置，第二天还能叫
跑法：python -B scripts/test_wake_dsh_slots.py
"""
import datetime
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "duty"))

import duty.duty_engine as de       # noqa: E402
import duty.wake_slots as WS        # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="wake-selftest-"))
de.WAKE_STATE = TMP / "state.json"
de.WAKE_LOG = TMP / "wake.log"
de.WAKE_OUT = TMP / "outbox"

calls = []
de._ring_dsh = lambda slot, label, text, kind="lead": (
    calls.append(f"{kind}:{slot}"), (True, "stub"))[1]
de.decision = lambda s: None


def at(y, mo, d, hh, mm, ss=0):
    de.now = lambda: datetime.datetime(y, mo, d, hh, mm, ss)


def main():
    ok = True

    def expect(cond, name, extra=""):
        nonlocal ok
        if cond:
            print("PASS %s" % name)
        else:
            print("FAIL %s -> %s" % (name, extra)); ok = False

    # ① 09:29:45（还差 5 秒）→ 不叫
    at(2026, 9, 14, 9, 29, 45)
    de.task_wake_dsh()
    expect(calls == [], "① 未到提前量不叫", calls)

    # ② 09:29:50（正点前 10 秒）→ 叫一次；再跑不重复
    at(2026, 9, 14, 9, 29, 50)
    de.task_wake_dsh(); de.task_wake_dsh()
    expect(calls == ["lead:09:30"], "② 提前 10 秒叫一次、当日不重复", calls)

    # ③ 09:30:30（正点后 30 秒；fire=09:29:50，grace=120s 内）→ 已有记档，不重复
    at(2026, 9, 14, 9, 30, 30)
    de.task_wake_dsh()
    expect(calls == ["lead:09:30"], "③ 响过就不再响", calls)

    # ④ 11:20（该叫时刻 10:59:50 已过 20 分钟）→ 超 grace，不补叫
    at(2026, 9, 14, 11, 20)
    before = list(calls)
    de.task_wake_dsh()
    expect(calls == before, "④ 过点超 grace 不补叫", calls)

    # ⑤ 18:29:50 → 18:30 复盘也叫得到（不受"16:00 后不补跑"影响）
    at(2026, 9, 14, 18, 29, 50)
    de.task_wake_dsh()
    expect("lead:18:30" in calls, "⑤ 18:30 也叫得到", calls)

    # ⑥ 周末（9/19 周六）→ 一次都不叫
    at(2026, 9, 19, 9, 29, 50)
    before = list(calls)
    de.task_wake_dsh()
    expect(calls == before, "⑥ 周末不叫", calls)

    # ⑦ 跨日重置：9/16 09:29:50 还能叫（状态里记的是 9/15）
    at(2026, 9, 16, 9, 29, 50)
    de.task_wake_dsh()
    expect(calls.count("lead:09:30") == 2, "⑦ 跨日自动重置", calls)

    print("RESULT:", "ALL PASS" if ok else "HAS FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
