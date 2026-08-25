# 项目目录说明

## 📂 目录结构

### `core/` - 核心代码
所有量化引擎的核心模块，包括策略、风控、执行、回测等。

### `config/` - 配置文件
- `risk_config.py`: 风控参数配置
- 其他配置文件

### `data/` - 用户数据
- `stock_lists/`: 股票列表缓存（如 stock_list.csv）
- `user_data/`: 用户自定义数据（如 myStock.csv）
- `raw_data/`: 原始数据备份

### `outputs/` - 运行输出
- `backtest_results/`: 回测结果
  - `performance/`: 绩效报表CSV
  - `charts/`: 图表文件（预留）
- `logs/`: 运行日志
- `orders/`: 订单流水记录

### `pybao/` - free-stockdb SDK
本地数据引擎的Python绑定，请勿修改。

## 📌 使用建议

1. **用户数据**：请将自定义的股票数据（如 myStock.csv）放入 `data/user_data/`
2. **股票列表**：系统生成的股票列表缓存自动保存在 `data/stock_lists/`
3. **回测结果**：每次回测的绩效报表保存在 `outputs/backtest_results/performance/`
4. **图表**：交互式图表由前端实时生成，可手动导出

## 🚀 快速启动

```bash
streamlit run app.py
```