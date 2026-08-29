# -*- coding: utf-8 -*-
"""在线财报确认调用（2026-08-30）——基于4轮探测证据的最佳推断
推断：get_fundamentals(query('finance').filter(代码), date=日期)
只调 1 次（消耗 1 次限额）——成功→打印字段/存缓存；失败→错误信息指引下一步
用法（Windows，老板拍板后跑）：python -B scripts/fundamentals_confirm.py
"""
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'pybao'))
import stock_sdk

CODE = '000063'
DATE = '2025-12-31'


def main():
    print(f"🔬 确认调用（消耗 1 次限额）：get_fundamentals(query('finance').filter(\"code = '{CODE}'\"), date='{DATE}')")
    try:
        q = stock_sdk.query('finance').filter(f"code = '{CODE}'")  # SQL条件版（SQLAlchemy线索：filter接受SQL表达式）
        r = stock_sdk.get_fundamentals(q, date=DATE)
        print(f"✅ 成功！类型: {type(r)}")
        if hasattr(r, 'head'):
            print(f"   形状: {r.shape}")
            print(f"   列: {list(r.columns)}")
            print(r.head(5).to_string())
            # 存缓存
            out = PROJECT_ROOT / 'data' / 'fundamentals_online'
            out.mkdir(exist_ok=True)
            r.to_csv(out / f'{CODE}.csv', index=False, encoding='utf-8')
            print(f"   💾 已存 {out / f'{CODE}.csv'}")
        else:
            print(f"   {str(r)[:800]}")
    except Exception as e:
        print(f"❌ 失败: {e}")
        print("   → 错误信息会指示下一步（换 statDate / filter 格式 / 代码格式）")


if __name__ == '__main__':
    main()
