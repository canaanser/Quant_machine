# -*- coding: utf-8 -*-
"""run_data_sync — 每日数据同步包装 (2026-09-10 老板定机制)
数据更新.exe 启动后不自动退出(完成看不出); 机制=等够时间(默认10分钟)后把它关掉,
数据库才算更新完成、后续扫描才能读到当日收盘。
用法: python -B scripts/run_data_sync.py [等待秒数=600]
"""
import subprocess, sys, time
from pathlib import Path

EXE = r"D:\a股数据\stockdb\数据更新.exe"
CWD = r"D:\a股数据\stockdb"
WAIT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 600


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(r"E:\stockgate\Quant_Alpha_System\outputs\data_sync_log.txt", "a",
                  encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    log(f"启动 数据更新.exe, 等待 {WAIT}s 后关闭(数据定稿)")
    try:
        p = subprocess.Popen([EXE], cwd=CWD)   # GUI 更新程序(非无窗也可, 让其在桌面可见进度)
        time.sleep(WAIT)
        # 若它自己已退出, taskkill 会报错无妨
        subprocess.run(["taskkill", "/PID", str(p.pid), "/F"],
                       capture_output=True, timeout=20)
        log("已关闭 数据更新.exe -> 当日数据同步完成")
    except Exception as e:
        log(f"sync 异常: {repr(e)[:120]}")


if __name__ == "__main__":
    main()
