# -*- coding: utf-8 -*-
"""emq_arch — 东财仿真账户·每日归档读取公共模块 (单一真源)
用于每日盘后: 最新交易日 / 可用现金 / 总资产。compose_daily_plan 与 gen_next_plan 共用, 勿重复实现。
"""
import csv
from pathlib import Path

ARCHIVE = Path(r"C:/Users/Administrator/.emgm3/tradedata/archive/31837988")
ACCOUNT = "a0de4b75-aae3-11f1-b535-52560acd7da0"


def latest_date():
    """最新含现金流水归档交易日 YYYYMMDD; 无则 None"""
    ds = []
    if ARCHIVE.exists():
        for day in ARCHIVE.iterdir():
            if (day / "downfiles" / ACCOUNT / "cash.csv").exists():
                ds.append(day.name.replace("-", ""))
    return max(ds) if ds else None


def read_cash(date):
    """读归档 cash.csv -> (available现金, nav总资产)"""
    d = date if len(date) == 10 else f"{date[:4]}-{date[4:6]}-{date[6:]}"
    p = ARCHIVE / d / "downfiles" / ACCOUNT / "cash.csv"
    with open(p, encoding="utf-8-sig") as f:
        for ln in csv.DictReader(f):
            return float(ln["available"]), float(ln["nav"])
    return 0.0, 0.0
