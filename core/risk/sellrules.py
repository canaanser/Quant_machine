# -*- coding: utf-8 -*-
"""卖出/风控规则唯一真源 (core/lib/sellrules.py) — ledger(实盘/模拟) 与 回测管道共用
消除"同一规则两处各写"的口径分叉。
口径(全部来自已验证回测):
  防崩 : 亏损 ≤ -12%        → 无条件卖(认错)
  峰顶 : 浮盈≥30% 后, 收盘跌破 持有期最高×0.98 且高位已≥5日 → 卖
  滞涨 : 浮盈≥30% 后, 连续15日不创新高 → 卖
  其余 : 拿住(浮盈未到30%别手痒)
"""
PNL_START = 0.30       # 启动峰顶跟踪的浮盈线
RETREAT = 0.98         # 破持有新高比例
HHD_HIGH = 5           # 高位≥5日(距新高天数)
STALL_DAYS = 15        # 滞涨天数
FANG_BENG = 0.88       # 防崩: 成本×0.88 = 成本-12%
FANG_BENG_PNL = -0.12  # 防崩跌幅


def pnl(cost, px):
    return px / cost - 1 if cost else 0.0


def decide(cost, px, peak, hhd):
    """返回 '防崩'/'峰顶'/'滞涨'/'hold'"""
    p = pnl(cost, px)
    if p <= FANG_BENG_PNL:
        return "防崩"
    if p >= PNL_START:
        if hhd >= STALL_DAYS:
            return "滞涨"
        if px < peak * RETREAT and hhd >= HHD_HIGH:
            return "峰顶"
    return "hold"


def fangbeng_price(cost):
    """防崩卖价(成本×0.88)"""
    return round(cost * FANG_BENG, 2)


def peak_trigger_price(cost):
    """进入峰顶跟踪的浮盈30%线(成本×1.30)"""
    return round(cost * (1 + PNL_START), 2)
