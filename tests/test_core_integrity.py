# -*- coding: utf-8 -*-
"""
配置与核心模块完整性测试（秒级，无数据依赖）
2026-08-26 小二陈：固化 config 合并 / DB_PATH 统一 / 形态注册表 21 种 等验收点
"""
import pytest


# ===== config 单一事实源 =====
class TestConfig:
    def test_commission_canonical(self):
        """佣金率必须为万一点二（老板拍板的规范值）"""
        from config.config import COMMISSION
        assert COMMISSION == 0.00012

    def test_db_path_unified(self):
        """PATTERN_DB_PATH 必须指向 pattern_history.db（DB_PATH 统一验收点）"""
        from config.config import PATTERN_DB_PATH
        assert PATTERN_DB_PATH.name == "pattern_history.db"
        assert PATTERN_DB_PATH.exists(), "数据库文件应存在"

    def test_scan_tickers_20(self):
        """扫描标的应为 20 只（老板指定清单）"""
        from config.config import SCAN_TICKERS
        assert len(SCAN_TICKERS) == 20
        assert "000063" in SCAN_TICKERS

    def test_weight_source_data(self):
        """权重来源应为数据驱动（data），legacy 可回退"""
        from config.config import WEIGHT_SOURCE
        assert WEIGHT_SOURCE == 'data'

    def test_config_reexports(self):
        """config/__init__.py 必须转发核心常量（导入路径兼容）"""
        from config import COMMISSION, INITIAL_CASH, SCAN_TICKERS, DEFAULT_RISK_CONFIG
        assert COMMISSION == 0.00012
        assert INITIAL_CASH > 0
        assert DEFAULT_RISK_CONFIG is not None


# ===== 形态注册表 =====
class TestRegistry:
    def test_21_patterns(self):
        """形态注册表应为 21 种（9→21 扩展验收点）"""
        from structure_engine.morphology import REGISTRY
        items = REGISTRY.list_all()
        assert len(items) == 21

    def test_patterns_have_id(self):
        """每个形态必须有 id（pattern_scanner 依赖）"""
        from structure_engine.morphology import REGISTRY
        for it in REGISTRY.list_all():
            assert 'id' in it and it['id']

    def test_new_atomic_classes_registered(self):
        """新增的原子特征类必须可实例化"""
        from structure_engine.morphology.atomic import (
            DirectionalBody, HammerDetector, PiercingDetector,
            StarDetector, ThreeMethodsDetector, ShadowBodyDetector,
        )
        for cls in [DirectionalBody, HammerDetector, PiercingDetector,
                    StarDetector, ThreeMethodsDetector, ShadowBodyDetector]:
            inst = cls()
            assert hasattr(inst, 'evaluate') or hasattr(inst, 'detect') or hasattr(inst, 'check')


# ===== 信号权重 =====
class TestSignalWeights:
    def test_direction_weight_in_range(self):
        """方向权重必须在 (0,1] 区间"""
        from structure_engine.signals.signal_weights import get_direction_weight
        for d in ('up', 'down', 'neutral'):
            w = get_direction_weight(d)
            assert 0 < w <= 1.0

    def test_weight_sources_both_valid(self):
        """legacy 与 data 两种权重来源都必须可取值"""
        from structure_engine.signals.signal_weights import get_direction_weight
        for src in ('legacy', 'data'):
            w = get_direction_weight('up', source=src)
            assert 0 < w <= 1.0


# ===== 关键模块导入冒烟（防拆包后 import 断裂） =====
class TestImports:
    def test_all_core_modules(self):
        import core.data_loader
        import core.strategy
        import core.backtest
        import structure_engine.scanner.data_writer
        import structure_engine.scanner.scanner_scheduler
        import structure_engine.cloud.electron_cloud_query
        import structure_engine.signals.signal_weights
        assert core.backtest.BacktestPipeline is not None

    def test_backtest_pipeline_mro(self):
        """BacktestPipeline 应组合三个 mixin（拆包验收点）"""
        from core.backtest import BacktestPipeline
        names = [c.__name__ for c in BacktestPipeline.__mro__]
        assert '_BacktestBase' in names
        assert '_PatternScanMixin' in names
        assert '_ExecutionMixin' in names

    def test_no_root_debris_scripts(self):
        """12 个开发期根目录脚本应已清理"""
        from pathlib import Path
        root = Path(__file__).parent.parent
        for f in ['deploy_structure_engine.py', 'clean_all.py', 'patch.py',
                  'test.py', 'test_db.py', 'check_600498.py', 'demo_scan.py',
                  'diagnose_patterns.py', '5module_csv.py', 'test_atomic_debug.py',
                  'test_csv_pattern_scan.py', 'main.py']:
            assert not (root / f).exists(), f"遗留脚本未清理: {f}"
