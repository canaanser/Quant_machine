# -*- coding: utf-8 -*-
"""watch_bridge — 看守→智能体 唤醒桥 (2026-09-10)
由会话以后台job托管: 常驻低耗检查关键事件, 一旦出现即退出(平台会把job结束推给智能体=唤醒)。
事件: ①当日orders_sent出现记录(14:44执行完成) ②引擎心跳中断>150s ③交易日15:08收盘。
用法: python -B scripts/watch_bridge.py
"""
import datetime, json, sys, time
from pathlib import Path
ROOT = Path(__file__).parent.parent
LOG = ROOT / "outputs"
HEART = LOG / "watch_heartbeat.txt"
SENT = LOG / "orders_sent.json"


def now():
    return datetime.datetime.now()


def hm():
    n = now()
    return n.hour * 60 + n.minute


def today_sent():
    try:
        if SENT.exists():
            d = now().strftime("%Y%m%d")
            return any(x.get("date") == d for x in json.load(open(SENT, encoding="utf-8")))
    except Exception:
        pass
    return False


def heart_age():
    try:
        return now().timestamp() - HEART.stat().st_mtime
    except Exception:
        return 10 ** 6


# 交易日唤醒时点(开盘叫醒 -> 盘中关键点 -> 收盘); 每次触发即退出, 由智能体处理后重启等下一个点
EVENTS = ["09:20", "10:00", "10:30", "11:15", "11:30",
          "13:10", "14:00", "14:30", "14:44", "15:08"]


def main():
    print(f"[watch_bridge] 启动 {now():%Y-%m-%d %H:%M:%S}", flush=True)
    while True:
        try:
            # 紧急: 引擎心跳中断即时唤醒
            if heart_age() > 150:
                print(f"[wake] 引擎心跳中断 {heart_age():.0f}s -> 唤醒处理", flush=True)
                return
            if now().weekday() > 4:          # 周末挂机(极低耗), 周一开盘自动醒
                time.sleep(600)
                continue
            # 消息桥: Codex投来的未处理任务 -> 立即唤醒(优先于时点)
            try:
                inbox = LOG / "inbox"
                if inbox.exists() and any(
                        x.suffix == ".json" and "task" in x.name for x in inbox.glob("*.json")):
                    print("[wake] inbox 新任务 -> 唤醒处理", flush=True)
                    return
            except Exception:
                pass
            m = hm()
            if m > 15 * 60 + 10:             # 收盘后待命, 不叫(次日自动挂到09:20)
                time.sleep(1800)
                continue
            nxt = None
            for ev in EVENTS:
                h, mi = map(int, ev.split(":"))
                em = h * 60 + mi
                if em > m:
                    nxt = em
                    break
            if nxt is None:                  # 已过全部事件但仍盘内(极少) -> 等
                time.sleep(30)
                continue
            remain = (nxt - m) * 60 - now().second
            if remain <= 0:                  # 到点 -> 唤醒退出
                print(f"[wake] 时点 {now():%H:%M:%S} -> 唤醒", flush=True)
                return
            time.sleep(min(remain, 30))      # 步进到点(30s内同时查心跳)
        except Exception as e:
            print(f"[watch_bridge] 检查异常 {repr(e)[:80]}", flush=True)
            time.sleep(30)

if __name__ == "__main__":
    main()
