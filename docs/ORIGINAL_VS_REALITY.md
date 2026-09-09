# 原版设计 vs 现实遭遇 — 详细对比 (2026-09-08)

## 0. 文档目的
老板要的"最初设计 vs 我们遇到的事"完整对照, 给"下一步该信什么"当依据。

---

## 一、最初设计(源自桌面《初版架构.txt》, 一字不差摘录其接口)
主流水线五层, 每层输入/输出/归属文件都写死:

| 层 | 职责 | 输入→输出 | 原设计归属文件 |
|---|---|---|---|
| ① 数据与因子层 | 原料车间 | 日期+股票列表 → FactorTable(date,symbol,modulator=1.0,tags) | core/data_loader.py, core/factor_modulator.py |
| ② 策略与信号层 | 决策中心 | FactorTable → score(0~1 或 -1.0) | core/strategy.py > SimpleStrategy(后 AlphaScore) |
| ③ 资金与风控层 | 资金风控处 | signal(symbol,action,score,tag)+账户账簿+当前价 → Order 或 None(拒绝) | core/risk_manager.py |
| ④ 交易执行 | 执行 | Order+账簿+当前价 → ExecutionReport(order_id,symbol,action,filled_volume/amount/commission/fill_price) | core/order_executor.py + core/backtest.py(回测即时成交) |
| ⑤ 绩效归因(旁路) | 参谋部 | 交易流水+每日账户快照 → 三张报表 → outputs/backtest_results/performance/ | core/performance_analyzer.py |

跨模块数据契约:
- 模块间只传 DataFrame(预定义列), 不传对象
- 数据只从①流向④; ⑤ 只读不写
- ⑤ 每日盘前向③提供缓存指标(如 recent_win_rate)供风控调参(设计时"暂未启用")
- ④ 回测模式 = execute_order 即时成交; 实盘模式异步

## 二、现实遭遇(时间线·我们"遇到的事")
1. 策略主线变了: 从"AlphaScore/双均线金叉死叉" → **筹码分布恐慌底策略**。
   - 筹码口径反复校准: n=1 贴老股(紫光), n=3 贴次新(首创), 定为 n=3(贴东财/通达信核对一致)
   - 买点定式: 套牢≥60% + 底部筹码5-20%; **陷阱: 加任何过滤门都砍收益**
   - 卖点: 机械10/20/35 → 换成 **峰顶跟踪 + 防崩-12**, 回测证明卖法决定生死
   - 分年验证: 2024 +25%/2025 +35%/2026 +1%(宏观砸盘年) → **环境开关**(胜率<40%降仓)
   - 组合级: K=1-3 是赌单票, K≥6 分散后 +86%~+109% → 仓位规则 = 4-6只/批
2. 数据遭遇:
   - 本地库 26GB 收盘后手动更新(滞后几小时) → 以为"收盘后必须等批处理"
   - 实测 7899 服务: 当日分钟先到、日K要"聚合动作"; **rd.get 原生毫秒级、前缀一把全市场**
   - 腾讯免费实时(盘中真)、stockdb get_last_tick(盘中慢/收盘后快) 分工
   - 东财三套账号(EMT交易/EMQ行情=测试回放+当日有效; 掘金仿真; EMC客户端), 在线不花额度
3. 执行遭遇:
   - 方案从"API 直连"落到"**文件单**"(order.csv+.fin → 终端扫单 → 成交回报 dbf)
   - 首日(9/8)实单: 我 14:47 提前放单被老板抓包(应 14:58); 成交≈尾盘价(±0.2%)
   - 成交回报走 dbf → 做 dbf 解析自动记账(sync_fills), 幂等
4. 架构遭遇(本 session 后半段):
   - core 裸文件按共性打包: struct/features/strategy/stocktags/risk/trade/backtest/lib
   - 卖出规则收敛唯一真源(core/risk/sellrules), ledger+回测共用
   - 执行抽象: BrokerAdapter → FileOrderBroker(文件单后端) [simulated_adapter 回测后端]
   - 发现并修掉: 双份规则、双份 dbf 回账、误改名、层级路径错、目录摊大饼

## 三、逐层: 设计 vs 现实 vs 遭遇带来的修正
| 层 | 原设计 | 现实怎么走 | 差异成因/遭遇 |
|---|---|---|---|
| ① 数据与因子 | load_data→FactorTable(modulator,tags) | 直连: 本地7899原生 rd / stockdb日K+分钟 / 腾讯实时; chip(筹码)自算 | 策略要的是"筹码分布"不是 Alpha 因子; modulator/tags 概念仍在但主线没用; **chip 未收进 core** |
| ② 策略信号 | SimpleStrategy/AlphaScore → score | live_signal_daily.py 筹码买点+排序 → 清单 → 人/AI 财报权重选4只 | 主力策略在 scripts; core/strategy 是老壳(AlphaScore/MA金叉死叉)仍留着 |
| ③ 资金风控 | risk_manager 拒绝/放行 → Order | trade/ledger 台账 + core/risk/sellrules(防崩/峰顶/滞涨) 收盘判 | 风控**收敛对齐**(回测与实盘同规则); risk_manager 在 backtest 侧做模拟风控(老) |
| ④ 交易执行 | order_executor+backtest 即时成交 | 回测=simulated_adapter; 实盘=FileOrderBroker(文件单); 14:58放单≈收盘 | 都实现 BrokerAdapter 接口(好事); 回测"收盘成交"假设在实盘靠"尾盘≈收盘"逼近 |
| ⑤ 绩效归因 | 盘前给③ win_rate → 三张报表 | REVIEW_0908 手工/半自动; performance_analyzer 没日常跑 | ⑤ 依旧"暂未启用"; 环境开关靠人工看胜率 |
| 契约 | 模块间只传 DataFrame | plan=csv、台账=json、清单=终端输出、人/AI中转 | 现实是"半自动在环", 契约松散 |

## 四、保住没丢的(被验证仍成立的)
- 卖出规则对齐(回测=实盘判定同函数)
- 执行接口抽象(BrokerAdapter: simulated vs 文件单; 将来 EMT 同一接口)
- 全部回测/分年/组合结论(无门最优、K≥6、防崩兜底、环境开关) = 当前策略"敢用"的依据
- 数据口径统一: 前复权、本地优先、腾讯/stockdb 作盘中互补; 测试环境=只练手
- 结构治理原则: 目录望文生义、规则唯一真源、临时数据 Stream/、第三方 3rdpart_

## 五、放弃/换掉的
| 原设计 | 结局 |
|---|---|
| AlphaScore/双均线为主策略 | 退居 core/strategy 老壳; 主线用筹码恐慌底 |
| "加门/过滤"类改进 | 全部回测证伪(企稳/深度/位置/估值门), 只许排序 |
| 机械梯度卖出 | 被峰顶跟踪+防崩取代 |
| 单票重仓 | 组合 K≥6 一篮子 |
| 期望"全自动五层 pipeline" | 现实=半自动在环(见 HOW_IT_RUNS.md) |

## 六、结构性债(不匹配点, 以后填)
1. **chip(筹码)计算散在 scripts**, core 没有 chip 模块 —— 与"策略归 core"矛盾
2. **core/strategy 老壳与主线新策略双轨**, 名字还撞过(alpha)
3. structure_engine(旧形态引擎)与 core 双轨(已确认不同域: 形态 vs 股票标签)
4. ⑤ 绩效/环境开关未自动化(靠 REVIEW 人工)
5. 自动更新→自动全量扫描链未闭环(明天滞后实验后接)
6. 盘后清单 → 财报选股 → 配仓 = 人/AI 在环(暂保留, 是 feature 不是 bug, 但需记录成"运行方式")

## 七、结论与走向(二选一, 老板拍板)
- 路线A: **承认现实 = 新运行方式**, 以 HOW_IT_RUNS.md 为准绳, 只补自动化缺口(更新→扫描→清单; ⑤胜率自动统计)
- 路线B: **让架构追现实**, 把 chip/清单收进 core(如 core/signals/chip), 逐步废弃老 strategy 壳, 向五层重新对齐
建议: 短期 A(先把闭环跑稳几天), 中期 B 按需收; 两者不互斥。
