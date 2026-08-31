# -*- coding: utf-8 -*-
"""
标签系统·可调用性验证（2026-08-30 小二陈）
============================================
验证 core/tags/ 标签系统：
  1. 标签池自动扫描注册（生成器即插即用）
  2. 生成震荡度/市值标签并落盘
  3. tag_at / filter / assemble / hierarchy 接口
  4. 标签数据独立存储，可回填

用法（Windows，python -B）：
    python -B scripts/verify_tags.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.tags import (produce, backfill, tag_at, filter,
                       assemble, hierarchy, list_tags, get)


def main():
    print("=" * 70)
    print("标签系统验证（core/tags/）")
    print("=" * 70)

    # 1. 标签池
    tags = list_tags()
    print(f"✅ 标签池自动扫描: {[t['name'] for t in tags]}")

    # 2. 生成落盘（幂等：已存在跳过）
    for tag in ['oscillation', 'marketcap']:
        p = produce(tag)
        print(f"✅ 生成 {tag}: {p}")

    # 3. 查询
    assert tag_at('000063', '2026-08-28', 'oscillation') == '震荡票'
    assert tag_at('000657', '2026-08-28', 'oscillation') == '趋势票'
    assert tag_at('000063', '2026-08-28', 'marketcap') == '大盘'
    print("✅ tag_at: 000063=震荡票/大盘, 000657=趋势票")

    # 4. 组装
    osc = filter(None, '2026-08-28', oscillation='震荡票')
    assert len(osc) == 26, f"震荡票应26只，实际{len(osc)}"
    osc_large = assemble('2026-08-28', {'oscillation': '震荡票', 'marketcap': '大盘'})
    print(f"✅ filter: 震荡票 {len(osc)} 只 | assemble: 震荡∩大盘 {len(osc_large)} 只")

    # 5. 层级
    h = hierarchy('oscillation', 'marketcap', '2026-08-28')
    assert '震荡票' in h and '趋势票' in h
    print(f"✅ hierarchy: 震荡票→{len(h['震荡票'])}个市值组, 趋势票→{len(h['趋势票'])}个市值组")

    # 6. 回填
    p2 = backfill('oscillation', overwrite=False)
    print(f"✅ backfill 幂等: {p2}")

    print("\n✅ 标签系统验证通过")


if __name__ == '__main__':
    main()
