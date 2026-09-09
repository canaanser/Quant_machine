# -*- coding: utf-8 -*-
"""值守看门狗 (watch_all_dog) — 每5分钟由计划任务拉起(全天)
duty_engine 是常驻进程(stockdb式): 若心跳过期(>8分钟, 即引擎挂了/没起来) → 拉起 duty_engine。
引擎自带单实例锁, 双拉也只活一个。watch_all 已退役, 仅留本兜底。
"""
import datetime, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
HEART = ROOT / "outputs" / "watch_heartbeat.txt"


def heartbeat_ok():
    try:
        ts = HEART.stat().st_mtime
        age = (datetime.datetime.now() - datetime.datetime.fromtimestamp(ts)).total_seconds()
        return age < 8 * 60
    except Exception:
        return False


if not heartbeat_ok():
    py = sys.executable or r"E:\python\量化看守.exe"  # 副本解释器, 进程名=量化看守
    subprocess.Popen([py, "-B", str(ROOT / "duty" / "duty_engine.py")],
                     cwd=str(ROOT), creationflags=0x08000000)  # CREATE_NO_WINDOW
    (ROOT / "outputs" / "watch_dog_log.txt").open("a", encoding="utf-8").write(
        f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] 心跳过期, 拉起 duty_engine\n")
