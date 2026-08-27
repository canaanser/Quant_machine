import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'pybao')
from stock_sdk import get_bars, get_all_securities

print("=== get_all_securities 按类型统计 ===")
secs = get_all_securities()
from collections import Counter
types = Counter(s.get('type') for s in secs)
print("类型分布:", dict(types))
print("\n=== 指数清单（type=index 前20）===")
idx = [s for s in secs if s.get('type') == 'index']
for s in idx[:20]:
    print(f"  {s.get('display_name')}  code={s.get('name')}  {s.get('start_date')}~{s.get('end_date')}")

print("\n=== get_bars 实际数值（上证指数）===")
for sec in ['000001.XSHG', '000300.XSHG', '399001.XSHE', '399006.XSHE']:
    try:
        bars = get_bars(sec, count=3, unit='1d')
        if bars is not None and len(bars):
            last = bars[-1]
            # dict 或 结构化数组
            if isinstance(last, dict):
                print(f"  {sec}: 最新 close={last.get('close')} date={last.get('date')}")
            else:
                print(f"  {sec}: 最新 = {list(last)[:6]}")
        else:
            print(f"  {sec}: 无数据")
    except Exception as e:
        print(f"  {sec}: 失败 {type(e).__name__}: {str(e)[:60]}")
