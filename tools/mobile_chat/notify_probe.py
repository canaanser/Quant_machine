# -*- coding: utf-8 -*-
r"""HUB-003 前置探针：手机看到的那套"叫醒通道"到底通不通（只读、不改任何设置）。

为什么先跑它：Service Worker 与系统通知都要求 **secure context**，
而手机访问的是 `http://100.64.75.72:8788`（Tailscale 明文 IP）。
没验证就盖楼，会重演 HUB-005 那个"决定要叫 ≠ 叫得醒"。

用法（Windows cmd）:
  E:\python\python.exe -B tools\mobile_chat\notify_probe.py [url]
默认 url = http://100.64.75.72:8788/
"""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://100.64.75.72:8788/"

JS = r"""
async () => {
  const out = {
    url: location.href,
    origin: location.origin,
    isSecureContext: window.isSecureContext,
    notificationApi: (typeof Notification !== "undefined"),
    notificationPermission: (typeof Notification !== "undefined") ? Notification.permission : null,
    serviceWorkerApi: !!navigator.serviceWorker,
    swRegister: null,
    note: null,
  };
  if (navigator.serviceWorker) {
    try {
      await navigator.serviceWorker.register("/sw-probe.js");
      out.swRegister = "ok";
    } catch (e) {
      out.swRegister = String(e && e.message || e);
    }
  }
  if (typeof Notification !== "undefined") {
    try {
      const p = await Notification.requestPermission();
      out.requestPermission = p;
    } catch (e) {
      out.requestPermission = "throw: " + String(e && e.message || e);
    }
  } else {
    out.requestPermission = "no-api";
  }
  return out;
}
"""


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        pg = ctx.new_page()
        try:
            pg.goto(URL, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            print("goto failed:", e)
            b.close()
            return 2
        try:
            res = pg.evaluate(JS)
        except Exception as e:
            res = {"evaluateError": str(e)}
        print(json.dumps(res, ensure_ascii=False, indent=2))
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
