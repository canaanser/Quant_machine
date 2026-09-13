# -*- coding: utf-8 -*-
"""把 avatars/ 里的 SVG 拼成一张样张（同时验证它们真能渲染、报裂图数）。只读素材、只写一张 PNG。

用法：E:\\python\\python.exe -B tools\\mobile_chat\\probes\\probe_avatars_preview.py
产物：outputs/dialog/avatars_preview.png（给人看风格用）
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
AV = os.path.join(ROOT, "tools", "mobile_chat", "avatars")
OUT = os.path.join(ROOT, "outputs", "dialog", "avatars_preview.png")

files = sorted(f for f in os.listdir(AV) if f.endswith(".svg"))
cells = "".join(
    '<figure><img src="../avatars/%s"><figcaption>%s</figcaption></figure>' % (f, f[:-4]) for f in files
)
html_tpl = (
    "<html><head><meta charset='utf-8'><style>"
    "body{margin:0;background:#12141a;color:#dfe3ea;font:13px/1.4 system-ui;padding:14px}"
    "h1{font-size:15px;margin:0 0 10px}"
    ".g{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}"
    "figure{margin:0;text-align:center}img{width:100%;border-radius:50%;display:block}"
    "figcaption{margin-top:4px;font-size:11px;color:#9aa3b2}"
    "</style></head><body><h1>HUB-AVATAR 素材样张（@@N@@ 张，按名册性别生成）</h1><div class='g'>@@CELLS@@</div></body></html>"
)
html = html_tpl.replace("@@N@@", str(len(files))).replace("@@CELLS@@", cells)
tmp = os.path.join(AV, "_preview.html")
open(tmp, "w", encoding="utf-8").write(html)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 560, "height": 460}, device_scale_factor=2)
    pg.goto("file:///" + tmp.replace("\\", "/"), wait_until="load")
    pg.wait_for_timeout(700)
    broken = pg.eval_on_selector_all("img", "n=>n.filter(e=>!e.complete||e.naturalWidth===0).length")
    pg.screenshot(path=OUT, full_page=True)
    print("样张:", OUT)
    print("裂图数:", broken, "/", len(files))
    b.close()
try:
    os.remove(tmp)
except Exception:
    pass
