# 老三样·新旧系统技术书 — V3.0(CTO接手前) vs 现在
(依据: 桌面《技术书/v3.0架构CTO版本.docx》《V3.0架构.html》 vs 当前仓库现状 docs/HOW_IT_RUNS.md、ORIGINAL_VS_REALITY.md)

## 一、V3.0(接手前)是什么
定位: **结构形态 + Alpha因子 的研究型系统蓝图**。分层:

| 层 | 模块 | 职责 | 输出 |
|---|---|---|---|
| 应用层 | app.py(Streamlit前端)/ main.py | 可视化+回测入口 | 图表/回测 |
| 执行层 | order_executor + simulated_adapter | 挂撤单/冻结/模拟成交 | ExecutionReport |
| 风控层 | risk_manager + standard_structures + dynamic_sizer | 止盈止损/仓位审批/动态仓位 | OrderTable |
| 策略层 | strategy.py(融合形态+因子) + signal_modulator(大盘过滤) | 决策 | SignalTable |
| 特征层(structure_engine) | detectors/ morphology/atomic+registry(11形态) scanner(wave/pattern/segment) voting(投票池+沉底) index_engine(特征向量+SQLite+余弦相似) factor_engine(板块强度+资金迁移) | 形态发现/投票/索引/因子 | StateTable(形态ID+强度+meta) |
| 数据层 | data_loader(multi-source: stockdb/akshare/yfinance/baostock) + data_structures(metadata: price/high/low/open/volume/benchmark/info) | 取数 | metadata.get_ohlc() |
| 横切 | config / factor_modulator(调制系数) / performance_analyzer(夏普/回撤/年化, nav.csv) / backtest.py(逐日滚动) / utils/kline_plotter / tests | 支撑 | 报表 |

核心契约: StateTable / SignalTable / OrderTable / ExecutionReport; 技术书 V3.1、第二张图 校对照。

## 二、现在是什么
定位: **可实盘演练的"筹码恐慌底组合策略"半自动执行系统**(见 HOW_IT_RUNS)。真跑链:
```
本地库/7899(日K+分钟) + 腾讯实时 → live_signal_daily(筹码n=3: 套牢≥60&底5-20,无门)
→ 人/AI 财报权重选4只 → plan → 14:58 FileOrderBroker(文件单→东财终端成交)
→ dbf回执 sync_fills 记台账 → ledger.status+core/risk/sellrules(防崩/峰顶/滞涨) → REVIEW复盘
```
支撑: 无门买点结论(企稳/深度/位置/估值门全证伪)、峰顶卖法+防崩-12(回测胜机械)、
分年验证(24 +25/25 +35/26 +1→环境开关)、组合 K≥6(分散 +86~+109%)、财报权重配仓。

## 三、逐层对照(旧 V3.0 → 现在 → 处置)
| V3.0 层 | 现在的对应 | 状态 |
|---|---|---|
| 应用层 app.py | **无看板**(P2 待建) | 旧 app.py 还在(引用 core.lib.views)但非日常入口 |
| 执行层 order_executor/simulated_adapter | backtest=simulated_adapter(回测域); 实盘=FileOrderBroker(文件单); 同 BrokerAdapter 接口 | 接口统一, 实盘后端新增 |
| 风控层 risk_manager+dynamic_sizer | 现: ledger(台账)+core/risk/sellrules(防崩/峰顶/滞涨); risk_manager 留在 backtest 做模拟风控 | 风控规则收敛唯一真源(回测=实盘); 动态仓位思想→K≥6 组合规则替代 |
| 策略层 strategy+signal_modulator | 主线=筹码信号(scripts); core/strategy 仍是旧壳(AlphaScore/MA)+调制器在 strategy | 策略换代, 旧壳待归档/改造 |
| 特征层 structure_engine | **遗留**: 形态/投票/索引/板块强度 在 structure_engine(仓库还在) | 未并入主线; 形态=另一域(见下) |
| 数据层 data_loader+metadata+pybao | 本地 stockdb/7899 原生 rd 为主 + 腾讯实时 + 3rdpart_pybao | 多源收窄为"本地权威+腾讯实时"; metadata/struct 仍存 |
| 绩效旁路 performance_analyzer | REVIEW_0908 手工 + 台账 | ⑤ 仍未自动化(债) |
| factor_modulator(调制系数) | 移到 core/strategy | 老概念, 主线不用(仍供旧管道) |
| kline_plotter/views | 并入 core/lib(utils绘图/views查看) | 沿用 |

## 四、两个世界的资产账
**V3.0 里有、现在还躺着的可用资产**(搁置≠废):
- structure_engine: morphology(11形态原子)、scanner(波段/形态)、voting、index_store(SQLite/相似) —— 形态投研资产, 与现在 features/trendline、volume_truth 同域不同深度
- tags 双轨澄清: core/stocktags(股票归类标签) ≠ structure_engine/morphology(形态检测)
- dynamic_sizer 的"仓位动态"思想 → 被"财报权重+组合K档"规则吸收
- metadata/OHLCV 结构 → core/struct + data_loader 仍在
**V3.0 没有、我们新增的**(这是本阶段价值):
- 筹码信号引擎(自算, 校准) + 一整套证伪实验(门/卖法/分年/组合)
- 实时层(腾讯/rt_stockdb/rt_watch)、执行层(文件单+broker+自动回账)、台账风控闭环
- 目录治理(按共性/分域/规则唯一真源/临时数据 Stream/第三方 3rdpart_)

## 五、一句话结论
- V3.0 = **形态结构 + Alpha 的研究蓝图**(那时候在"找能赚钱的形态");
- 现在 = **验证过的筹码恐慌底策略 + 能下单的管道**(在"把敢用的策略跑起来");
- 两者不是"坏了对", 是**时代不同**; 旧特征层资产(形态/投票/索引)哪天要重启形态线, 直接捡回来即可, 结构上不冲突(形态→features/未来因子, 股票标签→stocktags)。

## 六、遗留决定(等老板)
1. structure_engine 整块: 归档保留 or 择日并入 features(形态特征线)?
2. core/strategy 旧策略壳(AlphaScore/双均线): 归档 or 拆散?
3. app.py(Streamlit 旧前端): 废弃 or 翻新成新看板(P2)?
