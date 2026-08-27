# -*- coding: utf-8 -*-
"""
全量重扫结果验证脚本（2026-08-27 小二陈）

用法（Windows 上，项目根目录）：
    python scripts/verify_rescan.py

只读模式打开 pattern_history.db，输出：
  1. 总体统计：pattern/wave 总数、84 只完成度、缺失股票
  2. 逐股明细：日期范围（验证 10 年 / 新股对齐上市日）、9 个新字段填充率
  3. 完整性：wave 孤儿引用、重复 record_id

注意：扫描未跑完时运行会显示"缺失股票"（= 还没扫到的），属正常。
"""
import sys
import sqlite3
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "index_store" / "pattern_history.db"

# 与 config.config.SCAN_TICKERS 保持一致（优先动态读取，失败则提示）
sys.path.insert(0, str(PROJECT_ROOT))
try:
    from config.config import SCAN_TICKERS
    SCAN_TICKERS = list(SCAN_TICKERS)
except Exception as e:
    print(f"[警告] 无法从 config 读取 SCAN_TICKERS（{e}），只统计库内已有股票")
    SCAN_TICKERS = []

NEW_FIELDS = [
    "open_price", "return_1d", "return_2d", "return_3d", "return_4d", "return_5d",
    "drawdown_from_peak", "days_since_peak", "cooldown_days",
]


def main():
    if not DB_PATH.exists():
        print(f"[错误] 库不存在: {DB_PATH}")
        print("       请确认已运行扫描器（python -m structure_engine.scanner.scanner_scheduler --mode full）")
        return

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    # ---------- 1. 总体统计 ----------
    total_patterns = conn.execute("SELECT COUNT(*) FROM pattern_history").fetchone()[0]
    total_waves = conn.execute("SELECT COUNT(*) FROM wave_history").fetchone()[0]
    db_symbols = [r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM pattern_history ORDER BY symbol")]

    missing = [s for s in SCAN_TICKERS if s not in db_symbols]
    extra = [s for s in db_symbols if s not in SCAN_TICKERS]

    print("=" * 78)
    print("全量重扫验证报告")
    print("=" * 78)
    print(f"库文件        : {DB_PATH}")
    print(f"pattern 总数  : {total_patterns}")
    print(f"wave 总数     : {total_waves}")
    print(f"扫描池        : {len(SCAN_TICKERS)} 只")
    print(f"已完成        : {len(db_symbols)} 只")
    if missing:
        print(f"[待扫描/缺失] : {len(missing)} 只 -> {', '.join(missing)}")
    if extra:
        print(f"[库内多余]    : {len(extra)} 只 -> {', '.join(extra)}")
    print()

    # ---------- 2. 逐股明细 ----------
    print("逐股明细（日期范围 + 新字段填充率）:")
    header = (f"{'代码':<8}{'pattern':>8}{'wave':>6}{'首日':<12}{'末日':<12}"
              f"{'r1d%':>6}{'r5d%':>6}{'dd%':>6}{'cool%':>6}")
    print(header)
    print("-" * 78)

    for sym in db_symbols:
        row = conn.execute(
            "SELECT COUNT(*), MIN(match_date), MAX(match_date) FROM pattern_history WHERE symbol=?",
            (sym,),
        ).fetchone()
        cnt, dmin, dmax = row
        wcnt = conn.execute(
            "SELECT COUNT(*) FROM wave_history WHERE symbol=?", (sym,)
        ).fetchone()[0]
        fill = conn.execute(
            "SELECT "
            + ", ".join(f"SUM(CASE WHEN {f} IS NOT NULL THEN 1 ELSE 0 END)" for f in NEW_FIELDS)
            + ", COUNT(*) FROM pattern_history WHERE symbol=?",
            (sym,),
        ).fetchone()
        rates = [round(100.0 * fill[i] / fill[-1], 1) if fill[-1] else 0.0
                 for i in range(len(NEW_FIELDS))]
        dmin_s = dmin or "-"
        dmax_s = dmax or "-"
        print(f"{sym:<8}{cnt:>8}{wcnt:>6}{dmin_s:<12}{dmax_s:<12}"
              f"{rates[1]:>6}{rates[5]:>6}{rates[6]:>6}{rates[8]:>6}")

    # ---------- 3. 完整性 ----------
    print()
    print("=" * 78)
    orphan = conn.execute(
        """SELECT COUNT(*) FROM pattern_history ph
           LEFT JOIN wave_history wh ON ph.wave_id = wh.wave_id
           WHERE wh.wave_id IS NULL AND ph.wave_id IS NOT NULL"""
    ).fetchone()[0]
    dup = conn.execute(
        "SELECT COUNT(*) FROM (SELECT record_id FROM pattern_history GROUP BY record_id HAVING COUNT(*)>1)"
    ).fetchone()[0]
    print(f"wave 孤儿引用 : {orphan}（应为 0）")
    print(f"重复 record_id: {dup}（应为 0）")

    # 总体 9 字段填充率
    fill_all = conn.execute(
        "SELECT "
        + ", ".join(f"SUM(CASE WHEN {f} IS NOT NULL THEN 1 ELSE 0 END)" for f in NEW_FIELDS)
        + ", COUNT(*) FROM pattern_history"
    ).fetchone()
    print()
    print("全库 9 个新字段填充率:")
    for i, f in enumerate(NEW_FIELDS):
        r = 100.0 * fill_all[i] / fill_all[-1] if fill_all[-1] else 0.0
        print(f"  {f:<22} {r:6.1f}%  ({fill_all[i]}/{fill_all[-1]})")

    conn.close()
    print()
    print("验证完毕。若 pattern 从 2016 起、新字段填充率高、孤儿为 0，即重扫成功。")


if __name__ == "__main__":
    main()
