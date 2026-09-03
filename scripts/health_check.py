# -*- coding: utf-8 -*-
"""
名单体检单（Health Check）——文本版 demo（2026-09-02 老板：流程化，名单进→体检单出）
=====================================================================================
输入：一份股票名单（老板看上的票，≤10 只）
流程：① 取数自检（K线/daily估值/reports财报 齐不齐）
      ② 性格画像：震荡/趋势（近3年窗口）+ 王文五符合几项 + 估值贵贱
      ③ 每票体检：性格 → 建议灶台/控制 → 风险提示
      ④ 分组控制建议（趋势票/震荡票各用什么控制）
      ⑤ 名单总览风险提示
输出：文本体检单（报告类，不做预测，只给"性格→控制"诊断）

用法（Windows，python -B）：
    python -B scripts/health_check.py --tickers 603019,000977,600160
    python -B scripts/health_check.py --tickers 603019,000977,600160,002050,002837,001979,000786,002791
"""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

# ============ 工具函数 ============

def load_names():
    p = ROOT / 'data' / 'stock_names.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def classify_osc(px):
    """近3年性格：震荡/趋势（与 oscillation 标签同标准：center_stab<0.25 且 reg_corr<0 且 range<10）"""
    if len(px) < 250:
        return '数据不足'
    ma250 = px.rolling(250, min_periods=100).mean()
    if ma250.mean() <= 0:
        return '异常'
    center_stab = ma250.std() / ma250.mean()
    dev = (px / ma250 - 1).dropna()
    corr = dev.corr(pd.Series(np.arange(len(dev)), index=dev.index)) if len(dev) > 30 else 1.0
    hi, lo = px.max(), px.min()
    rr = hi / lo if lo > 0 else 999
    if center_stab < 0.25 and corr < 0 and rr < 10:
        return '震荡票'
    return '趋势票'


def wangwen_detail(sel, code, T):
    """王文五逐项判定，返回 (符合项数, 明细dict)"""
    ind = sel.latest_indicator(code, T) or {}
    pe, pb = sel.realtime_pe_pb(code, T)
    d = {}
    d['pe'] = pe
    d['pb'] = pb
    d['①低估值'] = pe is not None and 0 < pe < 30 and pb is not None and pb < 5
    ocf = ind.get('ocf_to_operating_profit')
    d['ocf'] = ocf
    d['②现金流'] = ocf is not None and ocf > 0.5
    gm = ind.get('gross_profit_margin')
    nm = ind.get('net_profit_margin')
    d['gm'] = gm
    d['nm'] = nm
    d['④毛利净利'] = gm is not None and gm > 20 and nm is not None and nm > 0
    ry = ind.get('inc_revenue_year_on_year')
    ny = ind.get('inc_net_profit_year_on_year')
    d['ry'] = ry
    d['ny'] = ny
    d['⑤双增长'] = ry is not None and ry > 0 and ny is not None and ny > 0
    n = sum(1 for k in ('①低估值', '②现金流', '④毛利净利', '⑤双增长') if d[k])
    return n, d


def fmt(v, dec=1):
    return '—' if v is None else f"{v:.{dec}f}"


def valuation_tag(pe, pb):
    """估值贵贱（王文五口径粗分）"""
    if pe is None:
        return '数据缺'
    if pe < 0:
        return '亏损'
    if pe < 30 and pb is not None and pb < 5:
        return '便宜'
    if pe > 100:
        return '极贵'
    if pe > 50:
        return '偏贵'
    return '中等'


def suggest_control(osc, ww_n, pe, ny):
    """性格+质量 → 建议灶台/控制（不预测，给已验证的控制组合）"""
    notes = []
    if osc == '震荡票':
        notes.append('灶台=震荡打法(价格带/MA20回归)，勿用趋势门猛买')
        notes.append('控制=低吸高抛，严仓位')
    else:  # 趋势票
        notes.append('灶台=趋势打法(金叉+multi门≥2)')
        notes.append('控制=无机械止损+止盈50%(让利润跑)，或少动多拿')
    if ww_n >= 3:
        notes.append('王文五≥3项=基本面稳健，可放心上灶')
    elif ww_n <= 1:
        notes.append(f'王文五仅{ww_n}项=基本面弱，投机属性强→仓位≤20%')
    if pe is not None and pe > 80:
        notes.append(f'pe={pe:.0f} 极贵，波动大→仓位≤20%')
    if ny is not None and ny < -30:
        notes.append(f'净利同比{ny:.0f}%=业绩下滑，防戴维斯双杀')
    return notes


# ============ 主流程 ============

def main():
    import argparse
    import logging
    parser = argparse.ArgumentParser(description="名单体检单（文本版）")
    parser.add_argument("--tickers", required=True, help="股票代码，逗号分隔（≤10只）")
    parser.add_argument("--date", default='2026-08-28', help="体检基准日")
    args = parser.parse_args()

    logging.disable(logging.CRITICAL)
    from core.data_loader import load_data
    from selection.wangwen import WangwenSelector

    codes = [t.strip().zfill(6) for t in args.tickers.split(',') if t.strip()]
    if len(codes) > 10:
        print(f"⚠️ 名单 {len(codes)} 只 > 10，本次只看前 10 只")
        codes = codes[:10]
    T = args.date
    names = load_names()

    # ① 取数
    md = load_data(source='freestockdb', tickers=codes, start='2023-01-01',
                   end='2026-08-27', frequency='1d', fq='qfq')
    sel = WangwenSelector()

    print("=" * 72)
    print(f"📋 名单体检单  {len(codes)} 只  |  基准日 {T}")
    print("=" * 72)

    # ② 性格画像 + ③ 每票体检
    print("\n【一、性格画像与每票体检】")
    print(f"{'代码':<7}{'名称':<8}{'性格':<6}{'王文':<5}{'pe':>7}{'pb':>6}{'估值':<6}{'净利yoy':>9}  诊断")
    print("-" * 90)
    report_rows = []
    for code in codes:
        px = md.price[code].dropna() if code in md.price.columns else pd.Series(dtype=float)
        # 近3年窗口
        seg3 = px[px.index >= (px.index[-1] - pd.DateOffset(years=3))] if len(px) else px
        osc = classify_osc(seg3)
        ww_n, d = wangwen_detail(sel, code, T)
        pe, pb = d['pe'], d['pb']
        vt = valuation_tag(pe, pb)
        ny = d['ny']
        diag = suggest_control(osc, ww_n, pe, ny)
        print(f"{code:<7}{names.get(code,'?'):<8}{osc:<6}{ww_n:<5}"
              f"{fmt(pe):>7}{fmt(pb):>6}{vt:<6}{fmt(ny):>9}  {'; '.join(diag[:2])}")
        report_rows.append({'code': code, 'osc': osc, 'ww': ww_n, 'diag': diag,
                            'pe': pe, 'pb': pb, 'ny': ny})

    # ④ 分组控制建议
    print("\n【二、分组控制建议（性格→灶台）】")
    trend_g = [r for r in report_rows if r['osc'] == '趋势票']
    osc_g = [r for r in report_rows if r['osc'] == '震荡票']
    other = [r for r in report_rows if r['osc'] not in ('趋势票', '震荡票')]
    if trend_g:
        print(f"\n趋势票组（{len(trend_g)} 只）: {', '.join(names.get(r['code'], r['code']) for r in trend_g)}")
        print("  → 灶台: 金叉 + multi门(≥2级共振)    控制: 无机械止损 + 止盈50% 或 拿住少动")
    if osc_g:
        print(f"\n震荡票组（{len(osc_g)} 只）: {', '.join(names.get(r['code'], r['code']) for r in osc_g)}")
        print("  → 灶台: 震荡打法(价格带/MA20回归)    控制: 低吸高抛，勿用趋势门猛买")
    if other:
        print(f"\n⚠️ 数据不足组（{len(other)} 只）: {', '.join(r['code'] for r in other)}——补数据后复检")

    # ⑤ 名单风险提示
    print("\n【三、名单总览风险提示】")
    ww_pass = [r for r in report_rows if r['ww'] >= 3]
    ww_weak = [r for r in report_rows if r['ww'] <= 1]
    expensive = [r for r in report_rows if r['pe'] is not None and r['pe'] > 80]
    declining = [r for r in report_rows if r['ny'] is not None and r['ny'] < -30]
    if ww_pass:
        print(f"✅ 基本面稳健({len(ww_pass)}只): {', '.join(names.get(r['code'], r['code']) for r in ww_pass)}")
    if ww_weak:
        print(f"⚠️ 基本面弱({len(ww_weak)}只,王文≤1): {', '.join(names.get(r['code'], r['code']) for r in ww_weak)}→仓位≤20%")
    if expensive:
        print(f"🔴 高估值({len(expensive)}只,pe>80): {', '.join(names.get(r['code'], r['code']) for r in expensive)}→波动大防回撤")
    if declining:
        print(f"🔴 业绩下滑({len(declining)}只,净利yoy<-30%): {', '.join(names.get(r['code'], r['code']) for r in declining)}→防戴维斯双杀")
    if not (ww_pass or ww_weak or expensive or declining):
        print("未见明显风险标签（数据齐全时）")
    print("\n" + "=" * 72)
    print("💡 本单是'性格→控制'诊断，不预测涨跌；实际收益由控制纪律保证，非选股能力。")
    print("=" * 72)


if __name__ == '__main__':
    main()
