# -*- coding: utf-8 -*-
"""清理 Stream/ 临时数据(T+1 落盘后调用)
删 Stream 全部内容(盘中临时产物), 保 outputs/ 台账等永久层不动。
用法: E:\python\python.exe -B scripts\clean_stream.py
"""
import shutil, sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
STREAM = ROOT / "Stream"


def main():
    if not STREAM.exists():
        print("Stream/ 不存在, 无需清理")
        return
    n = 0
    for item in STREAM.iterdir():
        if item.name == "README.md":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
        n += 1
    # 重建空子目录
    for sub in ("staging", "snapshots", "logs"):
        (STREAM / sub).mkdir(parents=True, exist_ok=True)
    print(f"已清理 Stream/ 共 {n} 项, 重建空子目录(README保留)")


if __name__ == "__main__":
    main()
