# -*- coding: utf-8 -*-
"""compose_daily_plan — 每日盘后自动生成次日 next_plan.csv (2026-09-09)
目标组合: 回测最优 6 只等权(单票≈净值/6)。
流程: 读东财每日归档 cash.csv(可用现金/净值) -> 持仓+当日收盘市值 -> 算出
      超配减仓(整手) 与 现金补位(候选顺序: PIT财报ROE优先+筹码分), 缺候选保护。
用法:
  python -B scripts/compose_daily_plan.py              预览(不写文件)
  python -B scripts/compose_daily_plan.py --write      写 outputs/next_plan.csv
  --date 20260909 指定基准日(默认=最新已归档交易日)
  --cash 0 覆盖现金(调试用; 默认读归档)
候选缓存: outputs/candidates_<date>.json(由 gen_next_plan.py --save-json 生成);
          缺失时只输出"减仓"部分并在尾部提示, 不写 buy(防拍脑袋乱补)。
护栏: outputs/STOP_AUTO 存在则不写; 卖出不超过持仓; 每只目标整手接近净值/6。
"""
import csv, json, sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core" / "lib"))
from core.lib.emq_arch import latest_date, read_cash


SLOTS = 6
BUFFER = 0.03            # 目标仓位后留3%现金缓冲


def close_px(codes, date):
    """本地7899 当日收盘价"""
    from core.lib import rdx
    out = {}
    for c in codes:
        rows = rdx.day_rows(c, date)
        if rows:
            out[c] = float(rows[0].get("close"))
    return out


def read_positions():
    from core.trade.ledger import _load
    return _load()["positions"]


def load_candidates(date):
    p = ROOT / "outputs" / f"candidates_{date}.json"
    if p.exists():
        return json.load(open(p, encoding="utf-8"))
    return None


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--cash", type=float, default=None)
    a = ap.parse_args()
    date = a.date or latest_date()
    cash, nav = read_cash(date)
    if a.cash is not None:
        cash = a.cash
    if (ROOT / "outputs" / "STOP_AUTO").exists():
        print("STOP_AUTO 存在 -> 不生成计划")
        return
    pos = read_positions()
    codes = list(pos.keys())
    px = close_px(codes, date)
    mv = sum(pos[c]["shares"] * px.get(c, pos[c]["cost"]) for c in codes)
    if nav <= 0:
        nav = mv + cash
    target = nav / SLOTS
    print(f"[{date}] nav={nav:.0f} 现金={cash:.0f} 持仓市值≈{mv:.0f} | 目标单票≈{target:.0f} (6只)")

    sells, buys = [], []
    # 1) 超配减仓(整手; 目标<1手不动; 卖出≥1手且留有余)
    for c in codes:
        sh = pos[c]["shares"]
        p = px.get(c)
        if not p or p <= 0:
            continue
        want = round(target / p / 100) * 100
        if want < 100:
            continue                 # 高价股目标不足1手 -> 保持现状
        if sh > want:
            sells.append((c, sh - want, p, pos[c].get("name", "")))
    sell_back = sum(sh * p for _, sh, p, _ in sells)
    remaining = cash + sell_back
    # 2) 候选补位到 ≤6 只
    cands = load_candidates(date)
    held = set(codes)
    if cands is None:
        print("候选缓存缺失(candidates_%s.json) -> 仅输出减仓, 不写买入(避免拍脑袋)" % date)
    else:
        for s in cands:
            c = s["code"]
            if c in held:
                continue
            if len(held) >= SLOTS:
                break
            p = s.get("px") or 0
            if p <= 0:
                continue
            want = round(target / p / 100) * 100
            if want <= 0:
                continue
            sh = min(want, int(remaining / p / 100) * 100)
            if sh <= 0:
                break
            buys.append((c, sh, p, s.get("name", "")))
            held.add(c)
            remaining -= sh * p
    # 输出
    print(f"建议卖出 {len(sells)} 笔(回笼≈{sell_back:.0f}):")
    for c, sh, p, nm in sells:
        print(f"  sell {c} {nm} -{sh}股 @收盘{p:.2f} ≈{sh*p:.0f}")
    print(f"建议买入 {len(buys)} 笔:")
    for c, sh, p, nm in buys:
        print(f"  buy  {c} {nm} +{sh}股 @收盘{p:.2f} ≈{sh*p:.0f}")
    if not a.write:
        print("(预览模式, 未写文件; --write 才写 next_plan.csv)")
        return
    with open(ROOT / "outputs" / "next_plan.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "side", "shares", "price", "name"])
        for c, sh, p, nm in sells:
            w.writerow([c, "sell", sh, round(p, 2), nm])
        for c, sh, p, nm in buys:
            w.writerow([c, "buy", sh, round(p, 2), nm])
    print(f"已写 outputs/next_plan.csv(卖{len(sells)} 买{len(buys)})")
    # 写后自动用引擎演练一遍(不真放单), 留痕
    import subprocess
    try:
        r = subprocess.run([sys.executable, "-B", str(ROOT / "duty" / "duty_engine.py"),
                            "--dryexec"], capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        print("dryexec:", (r.stdout or r.stderr)[-300:])
    except Exception as e:
        print("dryexec err:", repr(e)[:100])


if __name__ == "__main__":
    main()
