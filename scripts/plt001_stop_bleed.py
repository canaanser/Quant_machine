#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PLT-001 止血：把 [mcp_servers.deepseek_harness] 整段注释掉（不删除 → 可一键回滚）。

背景：该 MCP 会让 tool_search **重复发现同一个 deferred 命名空间**，
      请求里出现两份同名命名空间 → 被平台 400 拒收 → 那条线**永久锁死**。
      详见 docs/tasks/PLT-001.md、docs/LESSONS.md L2。

用法：
  python scripts/plt001_stop_bleed.py --check     # 只看状态，不改任何东西
  python scripts/plt001_stop_bleed.py --apply     # 备份 + 注释（幂等，带 TOML 校验）
  python scripts/plt001_stop_bleed.py --revert    # 从最近一次备份恢复
"""
import argparse
import os
import shutil
import sys
import time
import tomllib

CFG = r"C:\Users\Administrator\.codex\config.toml"
HEADER = "[mcp_servers.deepseek_harness]"
MARK = "# [PLT-001 止血 2026-09-11]"


def read_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().split("\n")


def find_block(lines):
    """返回 (start, end)：start=表头行下标；end=下一个表头行下标或文件末尾。"""
    start = None
    for i, line in enumerate(lines):
        if line.strip() == HEADER:
            start = i
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith("[") and s.endswith("]"):
            return (start, j)
    return (start, len(lines))


def check():
    lines = read_lines(CFG)
    blk = find_block(lines)
    if blk is None:
        print("状态: 该段不存在（已摘掉）")
        return 0
    s, e = blk
    active = not lines[s].lstrip().startswith("#")
    print("状态: %s   行 %d-%d" % ("[X] 仍生效（危险）" if active else "[OK] 已注释（止血生效）", s + 1, e))
    return 1 if active else 0


def apply():
    lines = read_lines(CFG)
    blk = find_block(lines)
    if blk is None:
        print("该段已不存在，无需处理。")
        return 0
    s, e = blk
    if lines[s].lstrip().startswith("#"):
        print("已经注释过，幂等退出。")
        return 0
    bak = CFG + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CFG, bak)
    print("备份:", bak)
    note = MARK + " 触发 tool_search 重复命名空间 -> 线被 400 锁死；原内容保留在下方，回滚去掉行首 # 即可"
    new = lines[:s] + [note] + ["# " + x for x in lines[s:e]] + lines[e:]
    with open(CFG, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(new))
    with open(CFG, "rb") as f:
        d = tomllib.load(f)
    print("TOML 校验: OK；mcp_servers =", list((d.get("mcp_servers") or {}).keys()))
    print("回滚: python scripts/plt001_stop_bleed.py --revert")
    return 0


def revert():
    d = os.path.dirname(CFG)
    prefix = os.path.basename(CFG) + ".bak-"
    baks = sorted(x for x in os.listdir(d) if x.startswith(prefix))
    if not baks:
        print("没有备份，无法回滚。")
        return 2
    latest = os.path.join(d, baks[-1])
    shutil.copy2(latest, CFG)
    with open(CFG, "rb") as f:
        tomllib.load(f)
    print("已从备份恢复:", latest)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--revert", action="store_true")
    args = ap.parse_args()
    sys.exit(revert() if args.revert else apply() if args.apply else check())
