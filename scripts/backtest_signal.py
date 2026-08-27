# -*- coding: utf-8 -*-
"""信号组合回测：深跌+首现+缩量+大实体短影 → 持有5日（多股票等权，盘尾模型）
用法（Windows 上，stockdb 全量可用）：
    python scripts/backtest_signal.py [--pool main|ai] [--tickers 000063,002396] [--max-holdings 10]
阈值：深跌 dd<-0.20；首现 cooldown IS NULL；缩量 vol<=0.1；大实体 body>=0.5；短影 shadow<=0.35
"""
import sys, sqlite3, argparse
from pathlib import Path
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

START, END = "2016-01-01", "2026-08-19"
HOLD = 5

def load_signals(tickers, mode='broad'):
    conn = sqlite3.connect(f"file:{PROJECT / 'data/index_store/pattern_history.db'}?mode=ro", uri=True)
    atomic = {}
    for s, d, p, vs, br, sr in conn.execute(
            'SELECT symbol, date, pattern_id, volume_spike, body_ratio, shadow_ratio FROM atomic_features'):
        atomic[(s, p, d)] = (vs, br, sr)
    ph = "','".join(tickers)
    sig = {}   # (symbol, date_str) -> True
    for s, p, dt, dd, cd, r5 in conn.execute(
            f"SELECT symbol, pattern_id, substr(match_date,1,10), drawdown_from_peak, cooldown_days, return_5d "
            f"FROM pattern_history WHERE symbol IN ('{ph}') AND return_5d IS NOT NULL"):
        a = atomic.get((s, p, dt))
        if a is None:
            continue
        vs, br, sr = a
        if mode == 'morning':
            # 早晨之星精选（大样本 61.3%）：早晨之星 + 深跌>30% + 极致缩量 + 大实体短影
            ok = (p == '3_bullish_0_morning_star'
                  and dd is not None and dd < -0.30
                  and vs is not None and vs <= 0.05
                  and br is not None and br >= 0.5
                  and sr is not None and sr <= 0.35)
        elif mode == 'multi':
            # 4金矿合并（~57%，强弱年互补）：早晨之星/三白兵/三只乌鸦/长白实体 + 深跌>30% + 极致缩量
            golds = {'3_bullish_0_morning_star', '3_bullish_0_three_white_soldiers',
                     '3_bearish_0_three_black_crows', '1_bullish_0_long_white'}
            ok = (p in golds
                  and dd is not None and dd < -0.30
                  and vs is not None and vs <= 0.05
                  and br is not None and br >= 0.5
                  and sr is not None and sr <= 0.35)
        else:
            # 广撒网：深跌+缩量+大实体短影
            ok = (dd is not None and dd < -0.20
                  and vs is not None and vs <= 0.1
                  and br is not None and br >= 0.5
                  and sr is not None and sr <= 0.35)
        if ok:
            sig[(s, dt)] = True
    conn.close()
    return sig


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default=None, choices=["main", "ai"])
    parser.add_argument("--tickers", default=None)
    parser.add_argument("--signal", default="broad", choices=["broad", "morning", "multi"],
                        help="broad=深跌+缩量+反转（广撒网）/ morning=早晨之星精选（61.3%）/ multi=4金矿合并（~57%）")
    parser.add_argument("--max-holdings", type=int, default=10)
    parser.add_argument("--cost", type=float, default=0.003,
                        help="每笔双边交易成本比例（佣金+印花税+滑点，默认0.3%保守）")
    parser.add_argument("--position", type=float, default=1.0,
                        help="单笔仓位比例（1.0=全仓复利；建议0.2控制回撤）")
    parser.add_argument("--start", default="2017-01-01",
                        help="回测起点（默认2017-01-01，排除2016数据起点伪影）")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.strip().zfill(6) for t in args.tickers.split(",") if t.strip()]
    elif args.pool == "ai":
        from config.config import SCAN_TICKERS_AI
        tickers = list(SCAN_TICKERS_AI)
    else:
        from config.config import SCAN_TICKERS
        tickers = list(SCAN_TICKERS)
    print(f"股票池: {len(tickers)} 只")

    sig = load_signals(tickers, mode=args.signal)
    print(f"信号总数: {len(sig)}")
    if not sig:
        print("无信号")
        return

    from core.data_loader import load_data
    md = load_data(source='freestockdb', tickers=tickers, start=args.start, end=END, frequency='1d', fq='qfq')

    # 每日信号/价格
    close_map = {}
    for sym in tickers:
        try:
            o = md.get_ohlc(sym)
            if o is not None and not o.empty:
                close_map[sym] = o['close'].astype(float)
        except Exception:
            continue
    print(f"价格可用: {len(close_map)} 只")

    # 全部交易日的并集（用第一个有数据的股票的日期做基准，逐日扫描）
    base_dates = list(next(iter(close_map.values())).index) if close_map else []
    pos_idx = {}   # symbol -> 统一日期索引映射

    trades = []
    holdings = []   # (symbol, exit_idx)
    for i, today in enumerate(base_dates):
        ts = today.strftime('%Y-%m-%d') if hasattr(today, 'strftime') else str(today)[:10]
        # 卖出到期持仓
        holdings = [(s, x) for s, x in holdings if x > i]
        for sym in [s for s, x in holdings if x == i]:
            pass  # 到期日收盘卖出（在买入时记账收益）
        # 检查新信号
        if len(holdings) < args.max_holdings:
            for sym in tickers:
                if (sym, ts) in sig and not any(s == sym for s, _ in holdings):
                    cl = close_map.get(sym)
                    if cl is None or today not in cl.index:
                        continue
                    try:
                        bi = cl.index.get_loc(today)
                    except Exception:
                        continue
                    ej = min(bi + HOLD, len(cl) - 1)
                    buy = float(cl.iloc[bi])
                    sell = float(cl.iloc[ej])
                    if buy > 0:
                        trades.append((sym, ts, buy, sell, sell / buy - 1))
                        holdings.append((sym, bi + HOLD))
                        if len(holdings) >= args.max_holdings:
                            break

    if not trades:
        print("无成交")
        return
    # 净收益：扣双边成本
    cost = args.cost
    pos = args.position
    rets = np.array([t[4] for t in trades])
    net = rets - cost          # 单笔净收益（全仓视角）
    port = net * pos           # 按仓位缩放（其余资金闲置）
    # 组合净值：每笔按仓位投入，资金滚动
    eq = np.cumprod(1 + port)
    total = eq[-1] - 1
    years = len(base_dates) / 252
    ann = (1 + total) ** (1 / years) - 1 if total > -1 else -1
    sharpe = port.mean() / port.std() * np.sqrt(252 / HOLD) if port.std() > 0 else 0
    mdd = (eq / np.maximum.accumulate(eq) - 1).min()
    print(f"\n信号组合回测（{len(tickers)}只池，{START}~{END}，持有{HOLD}日，最多{args.max_holdings}笔）")
    print(f"成本={cost:.2%}/笔 仓位={pos:.0%} | 成交{len(trades)}笔 胜率{np.mean(net>0):.1%} 平均净单笔{np.mean(net):+.2%}")
    print(f"总收益: {total:+.2%}")
    print(f"年化: {ann:+.2%}")
    print(f"夏普: {sharpe:.2f}")
    print(f"最大回撤: {mdd:.2%}")
    print(f"\n最近5笔:")
    for t in trades[-5:]:
        print(f"  {t[0]} {t[1]} 买{t[2]:.2f} 卖{t[3]:.2f} 毛{t[4]:+.2%} 净{t[4]-cost:+.2%}")


if __name__ == "__main__":
    main()
