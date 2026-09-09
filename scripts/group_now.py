# -*- coding: utf-8 -*-
"""115只命中票按申万一级行业分组(2026-09-06) cmd 权威跑"""
import sys
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "3rdpart_pybao"))

codes = [c.strip() for c in
         open(PROJECT_ROOT / "outputs/bigcap_now_codes.txt").read().split() if c.strip()]

info = {}
lines = open(PROJECT_ROOT / "outputs/bigcap_now.txt", encoding="utf-8").read().splitlines()
start = False
for ln in lines:
    if ln.startswith("✅"):
        start = True
        continue
    if ln.startswith("⚠️") or ln.startswith("==="):
        start = False
        continue
    parts = ln.split()
    if start and len(parts) >= 7 and parts[0].isdigit():
        # 格式: code 名称... 日期 收盘 套牢 底筹码 距峰 (名称可含空格)
        name = " ".join(parts[1:-5])
        info[parts[0]] = {"name": name, "px": float(parts[-4]),
                          "trap": float(parts[-3]), "bot": float(parts[-2])}

try:
    from stock_sdk import bk
    mapping = bk.get(codes, 1, "name") or {}
except Exception as e:
    print("板块映射失败:", e)
    mapping = {}

groups = defaultdict(list)
for c in codes:
    inds = mapping.get(c) or ["?"]
    groups[inds[0]].append(c)

out = []
out.append(f"115只命中票 按申万一级行业分组\n")
for ind in sorted(groups, key=lambda x: -len(groups[x])):
    cs = groups[ind]
    out.append(f"\n== {ind} ({len(cs)}只) ==")
    for c in cs:
        i = info.get(c)
        if i:
            out.append(f"  {c} {i['name']:<9} 收{i['px']:.2f} 套牢{i['trap']:.0f}% 底{i['bot']:.0f}%")
txt = "\n".join(out)
print(txt)
open(PROJECT_ROOT / "outputs/bigcap_now_byind.txt", "w", encoding="utf-8").write(txt)
