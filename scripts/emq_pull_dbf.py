# -*- coding: utf-8 -*-
"""成交回读 CLI(薄封装) — 逻辑唯一真源: FileOrderBroker.sync_fills
用法: python -B scripts/emq_pull_dbf.py
"""
import io
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from core.trade.file_order_broker import FileOrderBroker


def main():
    br = FileOrderBroker()
    n = br.sync_fills()
    print(f"成交回读: 新增记账 {n} 笔 (去重见台账)")


if __name__ == "__main__":
    main()
