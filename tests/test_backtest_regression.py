# -*- coding: utf-8 -*-
"""
回测回归测试（重，需本地缓存数据）
2026-08-26 小二陈：固化 TrendStrengthStrategy 双均线在 000063 一年数据上的基线指标。
任何对回测引擎/策略/数据管线的改动，若改变这些指标即视为行为漂移。

基线来源：core/backtest.py 拆包前后双版本对比验证（逐位一致）
"""
import json
import pytest

from conftest import cache_available

pytestmark = pytest.mark.cache

# ===== 基线指标（000063, 2025-01-01 ~ 2026-07-31, TrendStrength 5/20, top10, 50万）=====
# 2026-08-28 更新2：修复合并列错位（SELECT * → 显式列名）后，strength 全量真实（real）时的基线。
# 注：0.10556 是"strength 读不了→无形态信号"的污染假象；0.07593 为有真实形态融合的结果。
# 形态融合目前在单标的上为负贡献 → 后续需调融合权重/信号质量（这是待办发现）。
BASELINE = {
    "total_return": 0.075928,
    "annual_return": 0.0495955132,
    "sharpe": 0.3124060110,
    "max_drawdown": -0.2739266623,
    "trades": 117,
}

TICKER = "000063"
START, END = "2025-01-01", "2026-07-31"


@pytest.fixture(scope="module")
def market_data():
    """加载缓存数据（HTTP 命中缓存，秒级）"""
    if not cache_available():
        pytest.skip("无本地缓存数据（data/cache/stockdb/*_1d.csv），跳过回测回归")
    from core.data_loader import load_data
    return load_data(
        source='freestockdb', tickers=[TICKER],
        start=START, end=END, frequency='1d', fq='qfq'
    )


@pytest.fixture(scope="module")
def engine(market_data):
    """跑一次完整回测"""
    from core.backtest import BacktestPipeline
    from core.strategy import TrendStrengthStrategy
    strategy = TrendStrengthStrategy(short=5, long=20, verbose=False)
    eng = BacktestPipeline(strategy, top_n=10, verbose=False)
    eng.run(market_data, initial_cash=500000)
    return eng


class TestBacktestRegression:
    def test_total_return(self, engine):
        assert engine.total_return == pytest.approx(BASELINE["total_return"], abs=1e-12)

    def test_annual_return(self, engine):
        assert engine.annual_return == pytest.approx(BASELINE["annual_return"], abs=1e-12)

    def test_sharpe(self, engine):
        assert engine.sharpe == pytest.approx(BASELINE["sharpe"], abs=1e-12)

    def test_max_drawdown(self, engine):
        assert engine.max_drawdown == pytest.approx(BASELINE["max_drawdown"], abs=1e-12)

    def test_trades_count(self, engine):
        assert len(engine.trades) == BASELINE["trades"]

    def test_equity_curve_shape(self, engine):
        """资金曲线应与交易日数一致"""
        assert engine.equity_curve is not None
        assert len(engine.equity_curve) > 300  # 一年约 382 交易日


class TestDataLoader:
    def test_market_data_shape(self, market_data):
        """缓存数据应含 1 只股票，382 交易日"""
        assert len(market_data.price.columns) == 1
        assert market_data.price.shape[0] > 300
        assert market_data.benchmark is not None
