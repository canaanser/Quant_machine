# -*- coding: utf-8 -*-
r"""网页正文读取 CLI (2026-09-08)
用法(Windows cmd, 装过 scrapling):
  E:\python\python.exe -B scripts\web_read.py <url> [--head 2000] [--save outputs\web\page.txt]
例: E:\python\python.exe -B scripts\web_read.py "https://emt.18.cn/down"
"""
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from plugins.webread import read_page


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    url = args[0]
    head = 3000
    save = None
    for i, a in enumerate(args):
        if a == "--head" and i + 1 < len(args):
            head = int(args[i + 1])
        if a == "--save" and i + 1 < len(args):
            save = Path(args[i + 1])
    t0 = time.time()
    print(f"[抓取] {url} ...", file=sys.stderr, flush=True)
    text = read_page(url)
    print(f"[完成] {time.time()-t0:.1f}s, 正文 {len(text)} 字符", file=sys.stderr)
    if save:
        save.parent.mkdir(parents=True, exist_ok=True)
        save.write_text(text, encoding="utf-8")
        print(f"[已存] {save}", file=sys.stderr)
    print(text[:head])


if __name__ == "__main__":
    main()
