# -*- coding: utf-8 -*-
"""PLT-006「待老板」门槛的**真渲染**探针：看它是否按门槛分两类显示。

用法：E:\\python\\python.exe -B tools\\mobile_chat\\probes\\probe_boss_gate.py "<带 token 的 URL>"
只读页面 DOM，不写任何真源。
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
    print("bossBar:", pg.eval_on_selector("#bossBar", "e=>e.className+' | '+e.innerText"))
    pg.evaluate(
        "()=>{const b=[...document.querySelectorAll('#bossBar button')]"
        ".find(x=>x.textContent.indexOf('详情')>=0); if(b)b.click();}"
    )
    pg.wait_for_timeout(500)
    for r in pg.eval_on_selector_all("#bossList .row", "n=>n.map(e=>e.innerText.replace(/\\s+/g,' '))"):
        print("  row:", r[:160])
    gates = pg.eval_on_selector_all("#bossList .gate", "n=>n.map(e=>e.textContent)")
    print("gate 行数:", len(gates))
    for g in gates[:4]:
        print("  gate:", g[:160])
    print("pageerror:", errs[:2])
    b.close()
