# -*- coding: utf-8 -*-
r"""网页正文读取器 core/webread.py (2026-09-08, 老板引入 Scrapling 后收编成常备能力)
解决"JS单页/反爬页面抓不到正文": 无头浏览器渲染后剥标签取文本。
依赖: E:\python 已装 scrapling[fetchers] + playwright chromium
用法: from core.webread import read_page, render
"""
import html
import re
import time

try:
    from scrapling.fetchers import DynamicFetcher
    _OK = True
except Exception:  # WSL/未装环境
    DynamicFetcher = None
    _OK = False


def render(url, wait_sec=6, timeout=45):
    """渲染页面, 返回渲染后的 HTML 字符串(失败返回 None)"""
    if not _OK:
        raise RuntimeError("scrapling 未安装: E:\\python -m pip install scrapling[fetchers]")
    page = DynamicFetcher.fetch(url, headless=True, network_idle=True, timeout=timeout * 1000)
    body = page.body
    raw = body.decode("utf-8", "ignore") if isinstance(body, bytes) else str(body)
    return raw


def to_text(raw_html):
    """HTML → 可读正文文本"""
    if not raw_html:
        return ""
    txt = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", raw_html, flags=re.S)
    txt = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h[1-6]>|</tr>", "\n", txt, flags=re.I)
    txt = re.sub(r"<[^>]+>", "", txt)
    txt = html.unescape(txt)
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    return txt.strip()


def read_page(url, wait_sec=6, timeout=45):
    """一步到位: 渲染并提取正文文本"""
    return to_text(render(url, wait_sec, timeout))
