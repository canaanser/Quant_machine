# -*- coding: utf-8 -*-
"""
回测回归测试（重，需本地缓存数据）
2026-08-26 小二陈：固化双均线策略在 000063 一年数据上的基线指标。
任何对回测引擎/策略/数据管线的改动，若改变这些指标即视为行为漂移。

2026-08-28 小二陈：基线策略由 TrendStrengthStrategy 换为 SimpleStrategy——
组合层面（84 只 10 年）趋势强度全面落败（收益 1/4、回撤 -80%、Sharpe 0.38），已删除。

基线来源：core/backtest.py 拆包前后双版本对比验证（逐位一致）
"""
import json
import pytest

from conftest import cache_available

pytestmark = pytest.mark.cache

# ===== 基线指标（000063, 2025-01-01 ~ 2026-07-31, SimpleStrategy 5/20, top10, 50万）=====
# 2026-08-28 更新4：MAX_SINGLE_POSITION_RATIO 0.80→0.20（老板拍板，防单票超配爆炸），
# 单票上限 20% 后仓位更分散：收益 10.88%→2.96%（单票池无分散效应，仓位被砍）、回撤 -15.5%→-6.8%。
# 2026-09-02 更新5：Windows 权威重跑（scripts/gen_baseline.py 生成，outputs/regression_baseline.json）
# 差异来源：仓位 0.20→0.30（老板拍板）+ 止损/止盈规范化 + 卖出链调整——行为已变，基线同步
BASELINE = {
    "total_return": -0.005997999999999948,
    "annual_return": -0.003971220234361694,
    "sharpe": 0.05332980037260013,
    "max_drawdown": -0.17330954268649823,
    "trades": 27,
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
    from core.strategy import SimpleStrategy
    strategy = SimpleStrategy(short=5, long=20, verbose=False)
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
