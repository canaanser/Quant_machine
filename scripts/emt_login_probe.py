# -*- coding: utf-8 -*-
"""EMT 测试柜台 全天候探测(登录探针) — 2026-09-08 深夜
env: EMT_USER / EMT_PWD(不落盘); 默认服务器 61.152.230.41:19088
跑在 3rdpart_py310(python3.10, 官方 vnemttrader 绑定)
"""
import os
import sys

LIB = r"E:\stockgate\Quant_Alpha_System\tools\3rdpart_emt_py\emt_api_python\lib\windows"
os.add_dll_directory(LIB)
sys.path.insert(0, LIB)
from vnemttrader import TraderApi


class Probe(TraderApi):
    def __init__(self):
        super().__init__()


def main():
    user = os.environ.get("EMT_USER", "")
    pwd = os.environ.get("EMT_PWD", "")
    ip, port = "61.152.230.41", 19088
    api = Probe()
    api.createTraderApi(9, os.getcwd(), 4)   # client_id 9: 探测用
    api.setSoftwareVersion("probe-night")
    api.subscribePublicTopic(2)
    session = api.login(ip, port, user, pwd, 1, "127.0.0.1")
    err = api.getApiLastError() if hasattr(api, "getApiLastError") else None
    print(f"login session={session} (0=失败)")
    print(f"lastError={err}")
    if session and session != 0:
        print("→ 测试柜台【夜间可登录】")
        try:
            q = api.queryAsset(session, 1)
            print(f"queryAsset 返回码={q} (0=请求受理)")
        except Exception as e:
            print("queryAsset 异常:", repr(e)[:120])
        import time; time.sleep(2)
        api.logout(session)
    else:
        print("→ 测试柜台【夜间登录失败/未开】 (待交易时段再验)")


if __name__ == "__main__":
    main()
