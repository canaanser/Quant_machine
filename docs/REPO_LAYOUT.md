# 仓库目录(极简版, 2026-09-08)
```
core/  (已无裸露 .py, 全部按共性打包)
  struct/     数据结构(data_structures/standard_structures)
  features/   特征与形态(volume_truth量能特征, trendline趋势形态) — 英文直白: features
  backtest/   回测域: 管道/模拟撮合(risk_manager/order_executor/simulated_adapter)/绩效(performance_analyzer)
  trade/      实盘/模拟盘执行域: ledger台账/rtfeed行情/base_adapter接口 + file_order_broker(文件单执行后端)
  data_loader/ 数据取数  profile/ 股票档案
  strategy/  策略消费者 + 引擎调制器(factor_modulator/signal_modulator, 供回测管道) + AlphaScoreStrategy
  stocktags/  股票标签(震荡/王文五等个股归类; 与 structure_engine/morphology 的"形态检测"不同域)
  risk/       ③资金与风控层: 卖出/风控规则(sellrules: 防崩-12/峰顶/滞涨) ← 核心规则, 不属工具
  lib/        公共库(dbfread/orderfile/quotes/rdx + utils绘图/views查看 + logger基础设施)
plugins/     外围能力插件(网页读取等)
scripts/     全部用例脚本(生产/测试/研究都在, 按文件名认, 不分子目录)
tools/       只放第三方/SDK(emt、py310、安装包等) — 不写代码
Stream/      盘中临时产物(快照/暂存单/日志), T+1 落盘后整清
outputs/     永久层: 台账/信号史/复盘/验证结果
experiments/ 基线实验(2026-09-07 策略基线等)
docs/        文档
data/        本地库相关
```
规则: 不建多余分类目录; 通用逻辑进 core/lib; 临时数据进 Stream/。
规则: 不建多余分类目录; 通用逻辑进 core/lib; 临时数据进 Stream/; **任何第三方(SDK/库/安装包)一律加 3rdpart_ 前缀**。

## 边界铁律(老板 2026-09-08)
- struct/ = 纯数据结构(只装"形", 无行为无决策)
- lib/    = 无状态工具/基础设施(机械转换/读取/IO, 不含买卖规则/信号/风控判断)
- 业务逻辑(规则/信号/资金/风控)只许进 risk|alpha|trade|backtest|strategy 对应域
- 评审每次新增: 往 struct/lib 塞业务逻辑 = 违规, 打回重放

## 职责限定(防"新垃圾场", 老板评审 2026-09-08)
- profile/ = 股票静态画像/基本面元数据(读); 不存动态因子/策略结果
- tags/    = 形态/信号原子标签; 只被 alpha/strategy 消费, profile 只读元数据; 不独立决策
- alpha/   = 因子生产者(含 trendline 检测); 不直读数据层、不下单
- strategy/= 策略消费者; 只消费 alpha/上层输入, 不绕过 alpha 直读 data_loader(现状已干净)
- struct/lib = 纯结构/纯工具; 往内塞业务逻辑=违规(铁律见上)

## 未纳入主线的遗留域(扫描发现, 2026-09-08)
- selection/         旧选池模块(chip_dip等, 部分仍被研究脚本用)
- structure_engine/   旧形态/结构引擎(cloud/morphology), 与 core/tags 疑似双轨标签系统 → 待确认去留
- tests/             测试脚本(compare_*)已存在; 与 scripts 研究脚本有复制
- experiments/history 大量历史研究脚本: 各脚本内嵌旧规则(含卖出规则副本) — 历史存档性质, 不并入 sellrules 以免改历史结论
待定: core/strategy/alpha.py(旧AlphaScoreStrategy) 与 core/alpha/(因子包) 同名歧义 → 建议旧模块更名 score
