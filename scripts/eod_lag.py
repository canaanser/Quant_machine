# -*- coding: utf-8 -*-
r"""收盘后 7899 服务滞后性测量 (2026-09-09 实验)
用法(Windows, 15:00 后跑):
  E:\python\python.exe -B scripts\eod_lag.py --codes 603256,301358,600519,000063
轮询直到"全部目标出现且分钟15:00根在"或超时(默认到16:30), 记录第一次出现时间。
不依赖任何手动更新程序 —— 验证服务是否自收当日数据+滞后多长。
"""
import io, json, sys, time, datetime
import urllib.request, urllib.parse
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = Path(__file__).parent.parent / "Stream/logs" / "eod_lag_log.txt"


def get(expr):
    url = f"http://127.0.0.1:7899/?cmd=get&t={urllib.parse.quote(expr)}&json=1"
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.loads(r.read())


def has_today_daily(code):
    raw = get(f"日k:{code}:*")
    # 统一处理 list / dict
    items = []
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, list) and len(x) > 1 and isinstance(x[1], dict):
                items.append(x[1])
            elif isinstance(x, dict):
                items.append(x)
    elif isinstance(raw, dict):
        items = [raw]
    for it in items:
        if str(it.get("date", ""))[:8] == "20260909":
            return True
    return False


def minute_last():
    """取 600519 今天分钟最后一根时间(14位)"""
    raw = get("分钟k:600519:20260909*")
    items = []
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, list) and len(x) > 1 and isinstance(x[1], dict):
                items.append(x[1])
            elif isinstance(x, dict):
                items.append(x)
    dates = [it.get("date") for it in items if it.get("date")]
    if not dates:
        return None
    return max(int(d) for d in dates)


def main():
    codes = sys.argv[1:] or ["603256", "301358"]
    print(f"[开始] {datetime.datetime.now():%H:%M:%S} 测量: 收盘后服务滞后(不跑更新程序)", flush=True)
    log = open(OUT, "a", encoding="utf-8")
    t_end = datetime.datetime.now().replace(hour=16, minute=30)
    seen_daily = set()
    seen_1500 = None
    deadline = datetime.datetime.now() + datetime.timedelta(hours=1, minutes=30)
    while datetime.datetime.now() < min(t_end, deadline):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] "
        new = False
        for c in codes:
            if c in seen_daily:
                continue
            try:
                if has_today_daily(c):
                    seen_daily.add(c)
                    line += f"日K{c}首现@{ts}; "
                    new = True
            except Exception:
                pass
        if seen_1500 is None:
            try:
                ml = minute_last()
                if ml:
                    t = str(ml)
                    if t[:8] == "20260909" and t[8:12] == "1500":
                        seen_1500 = ts
                        line += f"分钟15:00根首现@{ts}; "
                        new = True
                    elif ml:
                        line += f"分钟最新{t[8:12]}; "
            except Exception:
                pass
        if new or line.count(";") > 1:
            print(line, flush=True)
            log.write(line + "\n"); log.flush()
        if len(seen_daily) == len(codes) and seen_1500:
            print(f"[完成] 日K全到@{ts} 分钟15:00@{seen_1500} —— 服务自收当日数据确认!", flush=True)
            log.write(f"[完成] {line}\n"); log.flush()
            return
        time.sleep(20)
    print(f"[超时] 16:30/90min到: 日K到{len(seen_daily)}/{len(codes)}, 分钟15:00={'有' if seen_1500 else '无'}", flush=True)


if __name__ == "__main__":
    main()
