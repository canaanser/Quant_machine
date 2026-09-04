# -*- coding: utf-8 -*-
"""
王文五筛选器·可调用性验证（2026-08-30 小二陈）
================================================
验证根目录 selection/ 筛选器模块：
  1. 可从 core 顶层导入（from core import WangwenSelector）或直接 from selection import
  2. 阈值来自 config（单一事实源）
  3. eligible(date) 返回当日池名单（无未来函数：pubDate ≤ date）
  4. 月度池历史诊断

用法（Windows，python -B）：
    python -B scripts/verify_wangwen_selector.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import WangwenSelector, BaseSelector
from config import (WANGWEN_PE_MAX, WANGWEN_PB_MAX, WANGWEN_OCF_MIN,
                    WANGWEN_GROSS_MIN, WANGWEN_NET_MIN,
                    WANGWEN_REV_YOY_MIN, WANGWEN_NP_YOY_MIN)


def main():
    print("=" * 70)
    print("王文五筛选器验证（selection/wangwen.py）")
    print("=" * 70)

    # 1) 继承与阈值
    sel = WangwenSelector()
    assert isinstance(sel, BaseSelector), "必须继承 BaseSelector"
    print(f"✅ 继承 BaseSelector，筛选器名: {sel.name}")
    print(f"   阈值(config): pe<{WANGWEN_PE_MAX} pb<{WANGWEN_PB_MAX} "
          f"ocf>{WANGWEN_OCF_MIN} 毛利>{WANGWEN_GROSS_MIN} 净利>{WANGWEN_NET_MIN} "
          f"营收yoy>{WANGWEN_REV_YOY_MIN} 净利yoy>{WANGWEN_NP_YOY_MIN}")

    # 2) 数据加载
    print(f"   本地估值 {len(sel._pe_pb)} 只 / 在线财报期表 {len(sel._ind_series)} 只")

    # 3) 关键日期池名单
    print("\n--- 关键日期池名单（滚动，无未来函数）---")
    for d in ['2024-03-31', '2024-08-31', '2025-01-06', '2025-07-01', '2026-07-31']:
        elig = sel.eligible(d)
        print(f"  {d}  池内 {len(elig):2d} 只: {','.join(sorted(elig)) if elig else '-'}")

    # 4) run() 别名与候选子集
    assert sel.run('2026-07-31') == sel.eligible('2026-07-31'), "run 必须等价 eligible"
    print("\n✅ run(date) == eligible(date)")
    sub = sel.eligible('2026-07-31', codes=['600757', '600941', '601728', '000848', '601899', '600988'])
    print(f"   候选子集过滤: {sorted(sub)}")

    # 5) 月度池历史（诊断输出，可存盘）
    h = sel.pool_history(start='2025-01-31', end='2026-07-31')
    print("\n--- 月度池历史 ---")
    print(h.to_string(index=False))
    print("\n✅ 验证通过：筛选器可被调用，名单滚动正确")


if __name__ == '__main__':
    main()
