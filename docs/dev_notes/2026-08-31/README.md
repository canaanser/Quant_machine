# 开发记录 —— 2026-08-31

> **一句话总结**：标签归类系统 + 档案系统（股票=人）提交，实验A 旧卖逻辑批量验证

## 一、关键接口（今天设计/修改的）

| 接口名 | 位置 | 输入 | 输出 | 变更说明 |
|--------|------|------|------|----------|
| `BaseTagGenerator` | `core/tags/base.py` | codes/start/end | 标准标签 DataFrame | ✅ 新增：name/version/value_domain/extra_columns；normalize → TAG_COLUMNS(code/valid_from/valid_to/value/version) |
| `register/unregister/get/list_tags` | `core/tags/registry.py` | 生成器类 | 注册表 | ✅ 新增：自动扫描 core/tags/generators/；labels.json 写 data/info/tags/ |
| `load/produce/backfill/tag_at/filter/assemble/hierarchy` | `core/tags/engine.py` | tag/codes/date | 查询/组装结果 | ✅ 新增：CSV 长格式存储；**value 必须 astype(str)**（int/str 匹配坑） |
| `OscillationGenerator` | `core/tags/generators/oscillation.py` | codes | 震荡票/趋势票 | ✅ 新增：center_stab<0.25 且 reg_corr<0 且 range_ratio<10 → 震荡；start None 默认 2017-01-01 |
| `MarketCapGenerator` | `core/tags/generators/marketcap.py` | codes | 大盘/中盘/小盘 | ✅ 新增：total_mv≥1000e8/≥100e8 |
| `WangwenTagGenerator` | `core/tags/generators/wangwen_tag.py` | codes | 符合几项 0-4 + weak | ✅ 新增：与 selection/wangwen.py **完全独立**（阈值本地复制，无 cross-import）；pubDate≤T 无前视 |
| `BaseProfileReader` | `core/profile/base.py` | code/date | 档案 dict | ✅ 新增：ABC（name/read/read_many） |
| `KlineReader/FundamentalsReader/TagsReader/MetaReader` | `core/profile/readers/` | code/date | 各类档案 | ✅ 新增：各读各的互不依赖 |
| `StockProfile` `assemble()` `assemble_one()` | `core/profile/__init__.py` | codes/date/fields | {code: StockProfile} | ✅ 新增：虚拟组装不落盘；core/__init__ 导出 |
| `BacktestPipeline(..., old_sell=False)` | `core/backtest/*` | bool | 死叉直接卖 | 🔄 修改：实验A 开关（base/pipeline/execution_mixin 三处） |
| `scripts/run_simple_pool.py --old-sell` | scripts/ | flag | 对比回测 | 🔄 修改 |

## 二、数据结构（今天涉及的）

| 表/结构 | 位置 | 说明 |
|---------|------|------|
| `data/info/tags/data/{name}_{version}.csv` | 标签数据 | 长格式 code/valid_from/valid_to/value/version(+weak)；**data 归 data**（干湿分离） |
| `data/info/tags/labels.json` | 标签注册表 | registry 调用时写 |
| `data/info/tags/assembly/` | 组装目录 | TAGS_ASSEMBLY_DIR（config 预留） |

## 三、核心文件清单（今日创建/修改）

| 文件路径 | 状态 | 说明 |
|---------|------|------|
| `core/tags/{base,registry,engine,__init__}.py` + `generators/{oscillation,marketcap,wangwen_tag}.py` | 新增 | 标签系统 v1（提交 7dd1135/a1518b0） |
| `core/profile/{base,__init__}.py` + `readers/{kline,fundamentals,tags,meta}.py` | 新增 | 档案系统 v1（提交 ce1f6af） |
| `config/config.py` | 修改 | +TAGS_DIR/TAGS_DATA_DIR/TAGS_LABELS_PATH/TAGS_ASSEMBLY_DIR |
| `core/backtest/{base,pipeline}.py` `execution_mixin.py` | 修改 | +old_sell 参数（实验A） |
| `scripts/run_simple_pool.py` | 修改 | +--old-sell |
| `scripts/verify_tags.py` `verify_profile.py` | 新增 | 全链路验证 |

## 四、关键数据快照（今日跑出来的数字）

| 指标 | 数值 | 说明 |
|------|------|------|
| 震荡票/趋势票 | 26 / 57（83只） | 000063 震荡 / 000657 趋势 |
| 多标签组装 | 震荡∩王文五4项=6只；∩大盘=2只（600941/601728） | filter/assemble 验证 |
| 档案验证 | 000063 震荡/大盘/王文五3；000657 趋势/大盘/王文五4 | date=2026-08-28 |
| **实验A 旧卖逻辑（近2年 进攻 带止损）** | 84池 +15.81→**+36.43%** ✅；精选15 +74.81→69.82% ❌；000063 +0.96→+5.61% ✅ | 见下决策 |

## 五、今日问题记录

| 问题 | 根因 | 状态 | 解决方案 |
|------|------|------|----------|
| produce start=None 崩溃 | None 覆盖 generator 默认值 | ✅ 已修复 | `start = start or '2017-01-01'` |
| 标签值 int/str 不匹配 | engine load 后 value 是 int64，比较用 str | ✅ 已修复 | `df['value'].astype(str)` |
| FUNDAMENTALS_DAILY_DIR NameError | 缺 import | ✅ 已修复 | config 导入补全 |
| git commit pathspec 失败 | labels.json 未生成（需先 list_tags()） | ✅ 已修复 | 先跑 registry 再提交 |

## 六、下一步计划（当日视角）

1. **[P0]** 趋势线 demo + 过滤器实验（次日 09-02 完成）
2. **[P1]** 王文五滚动池 + 底背离反转组合（DECISIONS §4.6 待办）

## 七、关键决策记录

| 决策 | 理由 | 决策时间 |
|------|------|----------|
| wangwen_tag 与 selection/wangwen.py 完全独立 | 老板：避免冲突/歧义（阈值本地复制，双处同源但互不 import） | 2026-08-31 |
| 档案虚拟组装不落盘 | 干湿分离：产物=运行时生成，功能/模块/数据/产物四层分离 | 2026-08-31 |
| 实验A 结论：84池旧版赢/精选15当前版赢 | 分治：普通票认错快，好票让利润跑（与次日趋势门结论互证） | 2026-08-31 |

## 八、废弃/待定区

| 条目 | 状态 | 结论 | 复用条件 |
|------|------|------|----------|
| 旧版直接卖（--old-sell）整体固化 | 🚫 暂废（只留开关） | 84池赢但精选15输 | 若按池分治（84池开/精选15关）可固化 |
| 凯利动态止损 / KalmanPID / PID 减仓 | 🚫 已删（更早，见 git 8816710 前） | 三机制全部验证负收益 | 已彻底移除，不恢复 |
