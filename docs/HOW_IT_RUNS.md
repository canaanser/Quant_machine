# 现状运行盘点 (2026-09-08) — 与原版架构的差异

## 每天实际怎么跑(按时间序, 无一行走"原版 pipeline")
```
【盘后 ~晚】本地库更新(老板自动更新程序, 26GB 批处理; 7899服务当日分钟/日K 会先到)
1. scripts/live_signal_daily.py    ← 630只大票(市值≥300亿, chip_mv_cache)
   每码 fetch_daily_qfq_single(本地SDK前复权) → 自写筹码分布(n=3换手衰减,贴东财校准)
   → 套牢≥60 & 底5-20(无门) → 排序 → 出"明日清单"(如9/7的17只)
2. 人/AI 在环: 按财报权重(东财F10 2026中报: 净利/营收同比/ROE/毛利/负债)
   从清单选 4只 → 定股数 → outputs/order_0908_plan.csv + ORDER_0908.md(纸面)
【盘中】盯盘/实时: rt_quotes(腾讯) / rt_stockdb(get_last_tick) / rt_watch(持仓防崩)
【14:58】scripts/final_order.py --go → FileOrderBroker.place_batch
   → C:\emq\scan\*.order.csv + .fin → 东财终端文件单扫单 → 仿真/实盘成交
【成交后】broker.sync_fills(emq_pull_dbf) 读 execution_report.dbf → 记 outputs/ledger.json
【每日盘后】ledger.status / rt_watch: core/risk/sellrules(防崩-12/峰顶/滞涨) → 该卖则卖
【复盘】REVIEW_0908.md 等: 人工/半自动记录; 胜率→环境开关(降仓) 尚未完全自动化
```
## 现在真正"活着"的模块(与层级)
| 环节 | 用的东西 | 在哪 |
|---|---|---|
| 信号 | 筹码分布买点(自写) | **scripts/** (live_signal_daily/回测脚本) — core 里没有 chip 模块! |
| 选股/配仓 | 财报权重 | 人/AI 在环(文档+plan), 无代码引擎 |
| 实时 | rt_quotes/rt_stockdb/rt_watch | scripts/ + core/trade/rtfeed + core/lib/quotes |
| 执行 | FileOrderBroker(文件单) | core/trade/ + core/lib/orderfile |
| 台账/风控 | ledger + sellrules | core/trade/ledger + core/risk/sellrules |
| 回测证据 | live_strategy_backtest/byyear/portfolio | scripts/(离线跑, 支持结论) |

## 与原版五层架构的差异
| 原版设计 | 现实 | 说明 |
|---|---|---|
| ①数据与因子 → 全在 pipeline 里喂 | 数据层直连(7899/腾讯) + chip 计算散在脚本 | chip 逻辑从未收进 core |
| ②策略与信号(AlphaScore/双均线金叉死叉) | **不是主力**; 主力=筹码恐慌底清单 | core/strategy 里是老策略壳, 新策略在 scripts |
| ③资金与风控(pipeline 内风控) | ledger+sellrules 独立台账, 与回测共享规则 | 风控已对齐(好事) |
| ④交易执行(回测即时成交) | 回测=模拟撮合(core/backtest), 实盘=文件单(broker) | 接口统一(BrokerAdapter), 但两套实现 |
| ⑤绩效归因旁路 | 只有手工 REVIEW/台账复盘 | performance_analyzer 存在但日常没跑 |
| DataFrame 契约/模块间只传表 | 脚本各自取数、plan=CSV、台账=JSON | 契约松散, 人/AI 中转 |

## 一句话
原版=“把 AlphaScore 因子策略全自动塞进五层管道”; 现实=“筹码信号清单 + 人/AI 定权重 + 文件单执行 + 台账风控”的**半自动在环流程**。策略换了, 架构文档没跟着换; 下一步要么把现实固化为新"运行手册"(本文件即起点), 要么按现实把 chip/清单收进 core 逐步对齐。不装看不见。

## 执行分工(2026-09-09 钉死)
| 用途 | 后端 | 说明 |
|---|---|---|
| 回测/研究(离线历史) | core/backtest + simulated_adapter(本地模拟撮合) | 与 EMT 无关; 卖出规则与实盘同源(core/risk/sellrules) |
| 模拟盘演练(实时虚拟) | FileOrderBroker → 掘金仿真文件单 | 白天撮合, 成交回执 dbf → sync_fills 记台账 |
| 实盘(将来) | EMT(实时下单, 专业投资者认证后) 或 实盘文件单 | 只执行, 不承载验证 |

要点:
- EMT 通道 **24h 在线**(登录/查询/下单通道凌晨实测通), 但 **A股撮合只在交易时段**; EMT 只支持实时下单,**无法回测** → 回测永远走本地模拟器, 结论→实盘只换 BrokerAdapter 后端。
