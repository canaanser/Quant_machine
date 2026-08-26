# 测试说明（2026-08-26 小二陈）

## 快速运行（推荐）

```bash
# 从项目根目录（WSL / Windows 均可）
python -m pytest -q
```

全部 26 个用例，约 12 秒（回测回归依赖本地缓存，命中缓存秒级）。

## 测试分层

| 文件 | 层级 | 耗时 | 依赖 |
|---|---|---|---|
| `tests/test_core_integrity.py` | 配置/注册表/导入冒烟 | 秒级 | 无 |
| `tests/test_morphology_unit.py` | 形态原子 + 扫描器单元 | 秒级 | 无 |
| `tests/test_backtest_regression.py` | 回测回归（基线固化） | ~12s | 本地缓存 `data/cache/stockdb/*_1d.csv` |

## 回测回归基线

固化 TrendStrengthStrategy(5/20) 在 000063（2025-01-01 ~ 2026-07-31）的指标：

- total_return = 0.065030
- annual_return = 0.042552
- sharpe = 0.294563
- max_drawdown = -0.279021
- trades = 148

**任何改动若改变这些指标 = 行为漂移**，测试即失败。基线来自 backtest.py 拆包前后双版本逐位一致验证。

## 注意事项

1. `tests/` 下其他 `test_*.py`（test_scanner_v2.py、compare_weight_backtest.py、test_scanner.py 等）是**历史独立脚本**（python tests/xxx.py 运行），不纳入 pytest（见 pytest.ini testpaths）
2. 无缓存数据时回测回归自动跳过（`pytest -m cache` 可单独标记；conftest 自动判断）
3. 新增核心逻辑时，建议同时在此固化断言（防回归）
