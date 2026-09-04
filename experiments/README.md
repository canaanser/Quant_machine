# 实验脚本归档（experiments/）

> 2026-09-02 老板"代码要整齐干净清晰"——scripts/ 只留正式主入口工具，
> 实验/分析/探测脚本按日期归档到此，git 历史保留完整（git mv），需要可找回。

## 目录说明

```
experiments/
├── 2026-09-02/    # 当日实验：样本外实测、技术面/王文五验证、止损止盈扫描等
└── history/       # 更早历史实验：探测/对比/形态验证/质量扫描等（保留备查）
```

## scripts/ 主入口（正式工具，未动）

| 脚本 | 用途 |
|------|------|
| `run_simple_pool.py` | 主回测入口（策略/趋势门/止损止盈/ww闸门 全参数） |
| `health_check.py` | 名单体检单（性格→控制诊断） |
| `out_of_sample.py` | 样本外实测（训练期选票→空仓起步验证） |
| `rand_pick.py` | 随机盲选池 |
| `fundamentals_fetch.py` | 本地 daily 估值拉取 |
| `fundamentals_online.py` | 在线财报拉取（旧格式，备用） |
| `fundamentals_online2.py` | 在线财报拉取（5表正确格式，--codes/--per-stock/--quarters） |
| `attribution_pool.py` | 股票池归因（按票盈亏） |
| `verify_tags.py` / `verify_profile.py` | 标签/档案系统验证 |
| `demo_trendline.py` / `compare_trend_gate.py` | 趋势线 demo / 过滤器对比 |
| `backfill_v3.py` / `wangwen_five.py` | 数据回填 / 王文五静态筛选 |

## 挪走的关键实验（experiments/2026-09-02/，若需复跑路径已变）

- `tech300_oos.py`：300只随机池样本外（技术面102只）
- `verify_ww_gate.py`：王文五双向闸门验证（84只池24只）
- `stat_fall_after_entry.py`：进场一路跌统计（退出机制依据）
- `scan_oos_stoploss.py`：样本外止损止盈扫描
- `attr_tech27.py` / `attr_oos_picks.py`：按票归因分析
- `test_simple_discipline.py`：简单纪律打法雏形（老板想法）
- `check_attribution.py`：归因自检
- `batch_fetch_kline.py`：批量拉K线（8进程）
- `scan_stopmatrix.py`：止损止盈网格

> 跑以上脚本用：`python -B experiments/2026-09-02/xxx.py`
