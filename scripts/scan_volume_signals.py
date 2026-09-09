# -*- coding: utf-8 -*-
"""量能验真信号扫描入口（2026-09-06 老板方法论固化 v0.1）
用法（WSL 或 Windows 均可，本地 stockdb HTTP）：
    python -B scripts/scan_volume_signals.py --tickers 000063,603606 --days 120
    python -B scripts/scan_volume_signals.py --tickers research_direction   # 研究方向池
    python -B scripts/scan_volume_signals.py --tickers 000063 --days 250 --end 2026-09-03
说明：换手率滚动分位(近180日)定低/中/高；A=低换手急跌(主力砸?) B=低换手急拉(试盘?)
     C=主力净流入+两侧量能放大(真启动?)。阈值待多票验证后调（2026-09-06 老板：先验证再调）。
"""
import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.features.volume_truth import scan_fake_moves, turnover_percentile_map

POOLS = {
    "research_direction": str(PROJECT_ROOT / "data/tickers/research_direction.txt"),
}


def main():
    ap = argparse.ArgumentParser(description="量能验真信号扫描")
    ap.add_argument("--tickers", required=True, help="逗号分隔代码 或 池名(research_direction)")
    ap.add_argument("--days", type=int, default=120, help="扫描最近 N 交易日")
    ap.add_argument("--end", default="2026-09-03", help="截止日")
    ap.add_argument("--names", default="", help="逗号分隔名称(可选，对齐显示)")
    args = ap.parse_args()

    if args.tickers in POOLS:
        codes = open(POOLS[args.tickers]).read().strip().split(",")
    else:
        codes = [c.strip().zfill(6) for c in args.tickers.split(",") if c.strip()]
    nmap = {}
    if args.names:
        nms = [n.strip() for n in args.names.split(",")]
        nmap = dict(zip(codes, nms))

    print(f"量能验真扫描 {len(codes)} 只 | 近{args.days}天 | 截止 {args.end}")
    print("=" * 78)
    for code in codes:
        sigs, _ = scan_fake_moves(code, nmap.get(code, code), days=args.days, end=args.end)
        name = nmap.get(code, "")
        print(f"\n--- {code} {name} 近{args.days}天 ---")
        if not sigs:
            print("   无显著信号")
            continue
        for tag, ds, chg, tv, net in sigs:
            print(f"   {ds} {tag:<28} {chg:+.1f}% 换手{tv:>6.2f}% 主力净{net/1e4:>+9.0f}万")


if __name__ == "__main__":
    main()
