# -*- coding: utf-8 -*-
"""
配置驱动回测入口（2026-09-02 架构整理 P2-3：换配置不换代码）
=====================================================================
用法（Windows）：
    python -B scripts/run_config_pool.py --config config/pipelines/pure_ma_tp30.yaml --pool 84
    python -B scripts/run_config_pool.py --config config/pipelines/simple_ww_gate.yaml --pool curated --tickers 000063
参数：
    --config   YAML 配置路径（config/pipelines/ 下）
    --pool     84=主池 / curated=精选15 / custom=用 --tickers
    --tickers  自定义代码（pool=custom 时）
"""
import sys
import io
import argparse
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    import logging as _logging
    parser = argparse.ArgumentParser(description="配置驱动回测")
    parser.add_argument("--config", required=True, help="YAML 配置文件路径")
    parser.add_argument("--pool", choices=['84', 'curated', 'custom'], default='custom')
    parser.add_argument("--tickers", default=None, help="自定义代码（pool=custom）")
    parser.add_argument("--start", default=None, help="覆盖起始日期")
    parser.add_argument("--end", default=None, help="覆盖结束日期")
    args = parser.parse_args()
    _logging.disable(_logging.CRITICAL)

    from core.backtest import BacktestPipeline, PipelineConfig

    config = PipelineConfig.from_yaml(args.config)
    errs = config.validate()
    if errs:
        print(f"❌ 配置非法: {errs}"); return

    # 决定 tickers
    if args.pool == '84':
        import config.config as cfg
        tickers = list(cfg.SCAN_TICKERS)
    elif args.pool == 'curated':
        import config.config as cfg
        tickers = list(cfg.SCAN_TICKERS_CURATED)
    else:
        tickers = [t.strip().zfill(6) for t in (args.tickers or '').split(',') if t.strip()]

    overrides = {'tickers': tickers}
    if args.start:
        overrides['start'] = args.start
    if args.end:
        overrides['end'] = args.end

    print(f"🚀 配置驱动回测: {config.name} | {len(tickers)} 只 | 池={args.pool}")
    eng = BacktestPipeline.from_config(config)
    with contextlib.redirect_stdout(io.StringIO()):
        eng.run_with_config(config, **overrides)
    print(f"✅ 完成: 累计 {eng.total_return:+.2%} | Sharpe {eng.sharpe:.2f} | "
          f"回撤 {eng.max_drawdown:.2%} | 交易 {len(eng.trades)} 笔")


if __name__ == '__main__':
    main()
