# -*- coding: utf-8 -*-
r"""核心6只 财报速拉+排序+配仓 (2026-09-08 老板授权在线财报)
源: 东财数据中心 RPT_F10_FINANCE_MAINFINADATA (快, 每票1请求)
用: E:\python\python.exe -B scripts\funda_rank6.py
输出: 各票 2026中报 营收/净利/同比 + ROE/毛利/净利率/负债率 → 财报分 → 权重(总半仓50%)
"""
import json, sys, time, urllib.request

CODES = [('688775', 'SH', '影石创新'), ('688702', 'SH', '盛科通信-U'),
         ('603256', 'SH', '宏和科技'), ('002595', 'SZ', '豪迈科技'),
         ('301358', 'SZ', '湖南裕能'), ('688172', 'SH', '燕东微')]


def get_secu(code, mkt):
    return f"{code}.{mkt}"


def fetch(code, mkt):
    url = ("https://datacenter.eastmoney.com/securities/api/data/v1/get"
           "?reportName=RPT_F10_FINANCE_MAINFINADATA&columns=ALL"
           f"&filter=(SECUCODE%3D%22{get_secu(code, mkt)}%22)&pageNumber=1&pageSize=8")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as r:
        j = json.loads(r.read().decode('utf-8'))
    rows = (j.get('result') or {}).get('data') or []
    return rows


def pick(rows, date):
    for r in rows:
        if str(r.get('REPORT_DATE', ''))[:10] == date:
            return r
    return None


def main():
    out = []
    for code, mkt, nm in CODES:
        rows = fetch(code, mkt)
        cur = pick(rows, '2026-06-30')
        py = pick(rows, '2025-06-30')   # 去年中报
        if cur is None:
            print(f"{code} {nm}: 无2026中报 (rows={len(rows)})"); out.append(None); continue
        g = lambda r, k: r.get(k)
        def num(v):
            try: return float(v)
            except (TypeError, ValueError): return None
        rev_c, rev_p = num(g(cur, 'TOTALOPERATEREVE')), num(g(py, 'TOTALOPERATEREVE'))
        np_c, np_p = num(g(cur, 'PARENTNETPROFIT')), num(g(py, 'PARENTNETPROFIT'))
        yoy_rev = (rev_c / rev_p - 1) * 100 if rev_c and rev_p else None
        yoy_np = (np_c / np_p - 1) * 100 if np_c is not None and np_p else None
        rec = dict(code=code, name=nm, mkt=mkt,
                   rev_y=round(yoy_rev, 1) if yoy_rev is not None else None,
                   np_y=round(yoy_np, 1) if yoy_np is not None else None,
                   rev=round(rev_c / 1e8, 1) if rev_c else None,
                   np=round(np_c / 1e8, 2) if np_c is not None else None,
                   roe=num(g(cur, 'ROEJQ')), gpm=num(g(cur, 'XSMLL')),
                   npm=num(g(cur, 'XSJLL')), debt=num(g(cur, 'ZCFZL')),
                   eps=num(g(cur, 'EPSJB')))
        out.append(rec)
        print(f"{code} {nm:<8} 中报: 营收{rec['rev']}亿(同比{rec['rev_y']}%) "
              f"归母{rec['np']}亿({rec['np_y']}%) ROE{rec['roe']} 毛利{rec['gpm']} "
              f"净利{rec['npm']} 负债{rec['debt']}%", flush=True)
    # 财报评分(6只内相对): 成长40%(净利同比+营收同比) 质量40%(ROE+毛利+净利) 稳健20%(负债低)
    valid = [r for r in out if r]
    def norm(vals):
        lo, hi = min(vals), max(vals)
        return [(v - lo) / (hi - lo) if hi > lo else 0.5 for v in vals]
    g_score, q_score, d_score = {}, {}, {}
    for key in ('g', 'q', 'd'):
        pass
    for r in valid:
        r['_g'] = (r['np_y'] or -99) * 0.7 + (r['rev_y'] or -99) * 0.3
        r['_q'] = (r['roe'] or -99) * 0.5 + (r['gpm'] or -99) * 0.3 + (r['npm'] or -99) * 0.2
        r['_d'] = -(r['debt'] or 99)
    ng = norm([r['_g'] for r in valid]); nq = norm([r['_q'] for r in valid]); nd = norm([r['_d'] for r in valid])
    for r, a, b, c in zip(valid, ng, nq, nd):
        r['score'] = round(0.4 * a + 0.4 * b + 0.2 * c + 1e-9, 3)
    tot = sum(r['score'] for r in valid)
    valid.sort(key=lambda r: -r['score'])
    print(f"\n排序(财报分, 由高到低) + 配仓(权重=总分50%内按分比例):")
    for i, r in enumerate(valid, 1):
        w = 50.0 * r['score'] / tot
        r['w'] = w
        print(f"{i}. {r['code']} {r['name']:<8} 财报分{r['score']:.2f}  配仓 {w:.1f}% "
              f"(净利同比{r['np_y']}% 营收同比{r['rev_y']}% ROE{r['roe']} 负债{r['debt']}%)")
    print(f"\n合计仓位: {sum(r['w'] for r in valid):.1f}% (半仓试探) | 平均每只 {50/len(valid):.1f}%")
    json.dump([{k: v for k, v in r.items() if not k.startswith('_')} for r in valid],
              open('outputs/funda_rank6.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
