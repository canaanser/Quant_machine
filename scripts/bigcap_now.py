# -*- coding: utf-8 -*-
"""大票池即时筹码扫描: 找当前触发纯筹码买点的票 (2026-09-04 收盘, 老板)
买点条件(基线): 套牢≥60% 且 5%≤底部筹码≤20%; 排ST/退市
输出: 命中票列表 + 接近命中(底20-30%) 参考
"""
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
from core.data_loader.freestockdb import fetch_daily_qfq_single


def last_chip_state(code):
    """返回最新交易日的 (date, close, trap%, bot5%, is_st, name)"""
    df = fetch_daily_qfq_single(code, "2023-01-01", "2026-09-05")
    if df is None or len(df) < 300:
        return None
    ca = df["close"].values; la = df["low"].values; ha = df["high"].values
    tv = df["turnover"].values
    is_st = df["is_st"].values if "is_st" in df.columns else None
    names = df["name"].values if "name" in df.columns else None
    hi_max = float(ha.max())
    w = max(hi_max * 0.0025, 0.01)
    nb = int(hi_max * 1.02 / w) + 1
    bins = np.arange(nb) * w
    chip = np.zeros(nb)
    last = None
    for i in range(len(df)):
        t = tv[i]
        if t > 0 and ha[i] > 0:
            alpha = min(t / 100.0 * 3.0, 1.0)   # 校准n=3(贴近东财, 2026-09-06)
            chip *= (1 - alpha)
            m = (bins >= la[i] - 1e-9) & (bins <= ha[i] + 1e-9)
            if m.any():
                chip[m] += alpha / m.sum()
        s = chip.sum()
        if s <= 0:
            continue
        c = chip / s
        p = ca[i]
        trap = c[bins > p].sum() * 100
        bot5 = c[(bins >= p * .95) & (bins <= p * 1.05)].sum() * 100
        pk = float(bins[int(np.argmax(c))])
        last = (str(df.index[i].date()).replace("-", ""), round(float(p), 2),
                round(float(trap), 1), round(float(bot5), 1), round(float(p / pk - 1) * 100, 1),
                bool(is_st[i]) if is_st is not None else False,
                str(names[i]) if names is not None else code)
    return last


def main():
    mv = json.load(open(str(PROJECT_ROOT / "outputs/chip_mv_cache.json")))
    big = sorted([c for c, v in mv.items() if v and v >= 300.0])
    print(f"大票池 {len(big)} 只, 扫最新筹码...", flush=True)
    hits, near, skip = [], [], 0
    t0 = time.time()
    for k, code in enumerate(big):
        st = last_chip_state(code)
        if st is None:
            skip += 1
            continue
        d, px, trap, bot5, pkd, ist, nm = st
        if ist or (nm.endswith("退") or "退市" in nm):
            continue  # ST/退市不碰
        if trap >= 60 and 5 <= bot5 <= 20:
            hits.append((code, nm, d, px, trap, bot5, pkd))
        elif trap >= 60 and 20 < bot5 <= 30:
            near.append((code, nm, d, px, trap, bot5, pkd))
        if (k + 1) % 100 == 0:
            print(f"  {k+1}/{len(big)} 耗时{time.time()-t0:.0f}s", flush=True)
    out = []
    out.append(f"\n===== 大票池即时筹码扫描(最新交易日≈2026-09-04) =====")
    out.append(f"\n✅ 触发买点(套牢≥60% & 底部5-20%): {len(hits)} 只")
    if hits:
        hits.sort(key=lambda x: -x[5])
        out.append(f"{'代码':<8}{'名称':<10}{'日期':<10}{'收盘':>8}{'套牢':>7}{'底筹码':>7}{'距峰':>7}")
        for code, nm, d, px, trap, bot5, pkd in hits:
            out.append(f"{code:<8}{nm:<10}{d:<10}{px:>8.2f}{trap:>7.1f}{bot5:>7.1f}{pkd:>+7.1f}")
    else:
        out.append("无命中")
    out.append(f"\n⚠️ 接近(套牢≥60% & 底部20-30%, 再洗一下可能到): {len(near)} 只")
    if near:
        near.sort(key=lambda x: x[5])
        for code, nm, d, px, trap, bot5, pkd in near[:25]:
            out.append(f"  {code} {nm} {d} 收{px:.2f} 套牢{trap:.0f}% 底{bot5:.0f}%")
    txt = "\n".join(out)
    print(txt, flush=True)
    open(str(PROJECT_ROOT / "outputs/bigcap_now.txt"), "w", encoding="utf-8").write(txt)


if __name__ == "__main__":
    main()
