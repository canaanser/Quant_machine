# -*- coding: utf-8 -*-
"""
候选标的"位置体检"（2026-08-27 小二陈）

用法（Windows 上，项目根目录）：
    python scripts/position_check.py

用 stockdb 最近 250 个交易日数据，算每只候选票的位置指标：
  - 距 250 日高点回撤 %     （深 = 在底部区域）
  - 250 日位置分位          （<30% = 低位）
  - 20 日涨跌幅             （转正 = 开始修复）
  - 年线（250MA）上下        （上 = 趋势修复，下 = 弱势）

状态判定：
  - 底部修复中：回撤深(-40%以下) + 20日转正
  - 底部磨底：回撤深 + 20日仍负
  - 回调中：回撤 -20%~-40%
  - 高位/强势：回撤小于 -20%
"""
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.data_loader.freestockdb import fetch_data_freestockdb

CANDIDATES = [
    ("002463", "沪电股份", "PCB"),
    ("300476", "胜宏科技", "PCB"),
    ("002130", "沃尔核材", "铜缆"),
    ("002837", "英维克", "液冷"),
    ("301018", "申菱环境", "液冷"),
    ("688387", "信科移动", "6G"),
    ("000063", "中兴通讯", "6G/光通信(池内)"),
    ("002792", "通宇通讯", "6G(池内)"),
    ("688041", "海光信息", "国产算力"),
    ("688256", "寒武纪", "国产算力(池内)"),
    ("600498", "烽火通信", "光通信(池内)"),
    ("600487", "亨通光电", "光通信(池内)"),
    ("601869", "长飞光纤", "光通信(池内)"),
]


def status_of(dd, ret20, pos):
    if dd <= -0.40 and ret20 is not None and ret20 > 0:
        return "底部修复中"
    if dd <= -0.40:
        return "底部磨底"
    if dd <= -0.20:
        return "回调中"
    return "高位/强势"


def main():
    codes = [c[0] for c in CANDIDATES]
    print("正在从 stockdb 加载数据（最近250交易日）...")
    md = fetch_data_freestockdb(codes, start="2025-08-01", end="2026-08-27", fq="qfq")

    print()
    header = (f"{'代码':<8}{'名称':<8}{'方向':<14}{'收盘':>9}{'回撤':>8}"
              f"{'分位':>7}{'20日':>8}{'年线':>6}  状态")
    print(header)
    print("-" * 88)

    for code, name, direction in CANDIDATES:
        try:
            df = md.get_ohlc(code)
            close = df["close"].astype(float)
            last = float(close.iloc[-1])
            high250 = float(close.max())
            low250 = float(close.min())
            dd = last / high250 - 1
            pos = (last - low250) / (high250 - low250) if high250 > low250 else 0.5
            ret20 = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) > 21 else None
            ma250 = float(close.mean())
            above = last > ma250
            st = status_of(dd, ret20, pos)
            ret20_s = f"{ret20 * 100:+.1f}%" if ret20 is not None else "-"
            print(f"{code:<8}{name:<8}{direction:<14}{last:>9.2f}{dd*100:>7.1f}%"
                  f"{pos*100:>6.1f}%{ret20_s:>8}{'上':>6}  {st}"
                  if above else
                  f"{code:<8}{name:<8}{direction:<14}{last:>9.2f}{dd*100:>7.1f}%"
                  f"{pos*100:>6.1f}%{ret20_s:>8}{'下':>6}  {st}")
        except Exception as e:
            print(f"{code:<8}{name:<8}{direction:<14}加载失败: {e}")

    print()
    print("说明：回撤=距250日高点跌幅；分位=250日区间位置；20日=近20日涨跌；年线=250日均线上下")
    print("目标：状态列为'底部修复中'或'底部磨底'的，是位置意义上的候选；再叠加您系统的位置/冷却信号确认")


if __name__ == "__main__":
    main()
