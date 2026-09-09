# -*- coding: utf-8 -*-
r"""EMQ L1 行情探针 (2026-09-08, 用官方 Python 绑定 vnemtquote, python3.10)
用法: 设好环境变量后:
  set EMQ_USER=540100061713 & set EMQ_PWD=... & tools\3rdpart_py310\python.exe -B scripts\emt_quote_probe.py
  (或直接 --user/--pwd 传参; 密码只在内存, 不落盘)
"""
import os, sys, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

EMT_LIB = r"E:\stockgate\Quant_Alpha_System\tools\3rdpart_emt_py\emt_api_python\lib\windows"
os.add_dll_directory(EMT_LIB)
sys.path.insert(0, EMT_LIB)
from vnemtquote import *

# 六个核心票: (ticker, 交易所 1沪/2深)
WATCH = [("603256", 1), ("688775", 1), ("301358", 2), ("002595", 2), ("688702", 1), ("688172", 1)]


class Probe(EMTQuoteApi):
    def __init__(self):
        super().__init__()
        self.md = {}

    def onDepthMarketData(self, market_data, bid1_qty_list, bid1_count, max_bid1_count,
                          ask1_qty_list, ask1_count, max_ask1_count):
        tk = market_data.get("ticker")
        if tk is not None and tk not in self.md:
            self.md[tk] = dict(market_data)

    def onDisconnected(self, reason):
        print("[disconnected] reason:", reason, flush=True)


def main():
    user = os.environ.get("EMQ_USER", "")
    pwd = os.environ.get("EMQ_PWD", "")
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--user" and i + 1 < len(args):
            user = args[i + 1]
        if a == "--pwd" and i + 1 < len(args):
            pwd = args[i + 1]
    ip, port = "61.152.230.216", 8093
    api = Probe()
    api.createPythonQuoteApi(101, "logs", 1, 3)   # 行情类型1=L1
    api.setHeartBeatInterval(5)
    print("version:", api.getApiVersion(), flush=True)
    ret = api.login(ip, port, user, pwd, 1, "127.0.0.1")   # TCP
    print("login ret:", ret, "(0=成功)", flush=True)
    if ret != 0:
        return
    for tk, ex in WATCH:
        api.subscribeMarketData([{"ticker": tk}], 1, ex)
    print(f"已订阅 {len(WATCH)} 只, 等 25 秒收快照...", flush=True)
    t0 = time.time()
    while time.time() - t0 < 25:
        time.sleep(1)
    if not api.md:
        print("未收到快照 —— 现在非交易时段正常, 连接已通即可; 开盘后再跑看数据", flush=True)
    for tk, ex in WATCH:
        if tk in api.md:
            m = api.md[tk]
            keep = {k: m[k] for k in m if any(s in k.lower() for s in
                    ("ticker", "last", "price", "open", "high", "low", "volume", "time"))}
            print(tk, "=>", keep, flush=True)
    api.logout()


if __name__ == "__main__":
    main()
