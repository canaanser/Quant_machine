# -*- coding: utf-8 -*-
"""王文五标准基本面筛选（2026-08-30 老板：事前标准选池——回答"怎么知道它是精选"）
数据：data/fundamentals_online/*.csv（valuation/indicator/income——84只全）
标准（日斗投资董事长王文）：
  ① 低估值：pe_ratio 低 + pb_ratio 低（安全边际）
  ② 高现金流：ocf_to_operating_profit（经营现金流/营业利润）> 0.5
  ③ 高分红：待补（分红接口未找到——标记）
  ④ 业务可持续：毛利率 gross_profit_margin + 净利率 net_profit_margin（盈利质量）
  ⑤ 有梦想（成长）：营收同比 inc_revenue_year_on_year + 净利同比 inc_net_profit_year_on_year > 0
打分：每项 0-1（按分位数），总分 5 项（③缺失暂算 4 项）
"""
import os
import json
import glob
import sys
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, 'data', 'fundamentals_online')


def latest_row(data_list):
    """取最新期（statDate/pubDate 最大）"""
    if not data_list:
        return None
    rows = sorted(data_list, key=lambda r: str(r.get('pubDate') or r.get('statDate') or ''), reverse=True)
    return rows[0]


def load_all():
    recs = []
    for f in glob.glob(os.path.join(OUT, '*.csv')):
        try:
            df = pd.read_csv(f, encoding='utf-8')
            code = str(df['code'].iloc[0]).zfill(6)
            val = json.loads(df['valuation'].iloc[0]) if 'valuation' in df.columns and pd.notna(df['valuation'].iloc[0]) else None
            ind = json.loads(df['indicator'].iloc[0]) if 'indicator' in df.columns and pd.notna(df['indicator'].iloc[0]) else None
            inc = json.loads(df['income'].iloc[0]) if 'income' in df.columns and pd.notna(df['income'].iloc[0]) else None
            recs.append({
                'code': code,
                'val': latest_row(val) if val else None,
                'ind': latest_row(ind) if ind else None,
                'inc': latest_row(inc) if inc else None,
            })
        except Exception:
            continue
    return recs


def score(recs):
    rows = []
    for r in recs:
        v, i, n = r['val'], r['ind'], r['inc']
        rows.append({
            'code': r['code'],
            'pe': (v or {}).get('pe_ratio'),
            'pb': (v or {}).get('pb_ratio'),
            'gross_margin': (i or {}).get('gross_profit_margin'),
            'net_margin': (i or {}).get('net_profit_margin'),
            'ocf_ratio': (i or {}).get('ocf_to_operating_profit'),
            'rev_yoy': (i or {}).get('inc_revenue_year_on_year'),
            'np_yoy': (i or {}).get('inc_net_profit_year_on_year'),
            'inc_return': (i or {}).get('inc_return'),
            'revenue': (n or {}).get('total_operating_revenue'),
        })
    df = pd.DataFrame(rows)

    def pct(s, reverse=False):
        q = s.rank(pct=True)
        return 1 - q if reverse else q

    # ① 低估值：pe/pb 越低越好（相对池内分位，反向）
    s_pe = pct(df['pe'], reverse=True).fillna(0.5)
    s_pb = pct(df['pb'], reverse=True).fillna(0.5)
    df['s_valuation'] = 0.5 * s_pe + 0.5 * s_pb
    # ② 现金流：ocf 比值越高越好
    df['s_cashflow'] = pct(df['ocf_ratio']).fillna(0.5)
    # ④ 质量：毛利率/净利率/ROE
    df['s_quality'] = (pct(df['gross_margin']).fillna(0.5) + pct(df['net_margin']).fillna(0.5)) / 2
    # ⑤ 成长：营收同比 + 净利同比
    df['s_growth'] = (pct(df['rev_yoy']).fillna(0.5) + pct(df['np_yoy']).fillna(0.5)) / 2
    df['total'] = df[['s_valuation', 's_cashflow', 's_quality', 's_growth']].mean(axis=1)
    return df


def main():
    recs = load_all()
    print(f"读取 {len(recs)} 只基本面\n")
    df = score(recs)
    df = df.sort_values('total', ascending=False).reset_index(drop=True)
    pd.set_option('display.width', 160)
    pd.set_option('display.max_columns', 20)
    print("=== 王文五标准评分（①②④⑤，③分红待补）Top30 ===")
    show = df.head(30).copy()
    for col in ('pe', 'pb', 'gross_margin', 'ocf_ratio', 'rev_yoy', 'np_yoy'):
        show[col] = show[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "-")
    print(show[['code', 'pe', 'pb', 'gross_margin', 'ocf_ratio', 'rev_yoy', 'np_yoy',
                's_valuation', 's_cashflow', 's_quality', 's_growth', 'total']].to_string(index=False))
    print(f"\n=== 全 84 只平均分: {df['total'].mean():.3f} ===")

    # ===== 绝对阈值版（王文五标准真语义：绝对标准，非相对分位）=====
    print("\n=== 王文五标准·绝对阈值版（①pe<30 ②ocf>0.5 ④毛利>20% ⑤营收&净利同比>0）===")
    th = df.copy()
    th['ok_val'] = (th['pe'] < 30) & (th['pb'] < 5) & (th['pe'] > 0)
    th['ok_cf'] = th['ocf_ratio'] > 0.5
    th['ok_q'] = (th['gross_margin'] > 20) & (th['net_margin'] > 0)
    th['ok_g'] = (th['rev_yoy'] > 0) & (th['np_yoy'] > 0)
    th['pass_n'] = th[['ok_val', 'ok_cf', 'ok_q', 'ok_g']].sum(axis=1)
    full = th[th['pass_n'] >= 4].sort_values('total', ascending=False)
    print(f"\n满足全部4项（估值/现金流/质量/成长）的票: {len(full)} 只")
    if len(full):
        for _, r in full.iterrows():
            print(f"  {r['code']}: pe={r['pe']:.1f} pb={r['pb']:.2f} 毛利={r['gross_margin']:.1f}% ocf={r['ocf_ratio']:.0f} 营收yoy={r['rev_yoy']:.0f}% 净利yoy={r['np_yoy']:.0f}%")
    pass3 = th[th['pass_n'] == 3].sort_values('total', ascending=False)
    print(f"\n满足3项（接近标准）: {len(pass3)} 只")
    for _, r in pass3.head(10).iterrows():
        print(f"  {r['code']}: pe={r['pe']:.1f} pb={r['pb']:.2f} 毛利={r['gross_margin']:.1f}% ocf={r['ocf_ratio']:.0f} 营收yoy={r['rev_yoy']:.0f}% 净利yoy={r['np_yoy']:.0f}%")

    # 输出 CSV
    df.to_csv(os.path.join(ROOT, 'data', 'wangwen5_score.csv'), index=False, encoding='utf-8')
    print("\n已存 data/wangwen5_score.csv")


if __name__ == '__main__':
    main()
