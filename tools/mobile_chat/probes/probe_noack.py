# -*- coding: utf-8 -*-
"""减法② 探针：公告发布入口的「免回执」开关在真页面上**是否真的生效**。只读 DOM。

用法：E:\\python\\python.exe -B tools\\mobile_chat\\probes\\probe_noack.py "<带 token 的 URL>"
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

url = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
    pg.goto(url, wait_until="load", timeout=30000)
    pg.wait_for_timeout(3500)
    pg.eval_on_selector("#targetSel", "e=>{e.value='全体';e.dispatchEvent(new Event('change'));}")
    pg.wait_for_timeout(300)
    chips = pg.eval_on_selector_all("#noticePick .np-chip", "n=>n.map(e=>e.textContent)")
    print("chips:", chips[:3], "...共", len(chips))
    pg.evaluate(
        "()=>{const b=[...document.querySelectorAll('#noticePick .np-chip')]"
        ".find(x=>x.textContent.indexOf('免回执')>=0); if(b)b.click();}"
    )
    pg.wait_for_timeout(300)
    print("勾了免回执后的标签:", pg.inner_text("#noticePick")[-40:])
    cls = pg.eval_on_selector_all(
        "#noticePick .np-chip", "n=>n.filter(e=>e.textContent.indexOf('免回执')>=0).map(e=>e.className)"
    )
    print("免回执 chip class:", cls, "（要含 on 才算真生效）")
    print("pageerror:", errs[:2])
    b.close()
