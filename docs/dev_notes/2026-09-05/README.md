# 开发记录 —— 2026-09-05（凌晨场）

> **一句话总结**：架构整理 P0 回归基线 + P1 闸门切割（WangwenGate/TagRouter）+ P2 配置层试水 → **老板拍板回退 P2**；随后定格"代码卫生后置原则"；凌晨 03:30 老板跑精选15 最佳配置出流水（验账）
>
> ⚠️ **本节由 2026-09-02/README.md 拆出**：§十六~§十七 实际 git 提交日期全在 **09-05 凌晨**（2bce2b1/e63c571/3646db0/876b107/e92f89f/ec756b6），原文档把跨 09-02→09-05 的补丁全堆在一个文件里（压缩后日期记账错误），按老板指示按 git 日期归入本日。节号沿用原编号，内容未改。
> 📌 节内标题所带"2026-09-02 老板：xxx"为**老板原话引用日**（拍板那天），文件归档日=09-05（git 提交日）；两者不一致属正常。

## 当日提交（git log，09-05 02:20~03:28）
- `164591c` 清理：删妖股/蓝筹止盈止损死代码（config+risk_manager），修复 pandas 3.0 弃用警告（state），前端止损止盈开关、拉取脚本 --codes/--per-stock/--quarters
- `011e5a6` 代码整理（老板：整齐干净清晰）2026-09-02
- `d4310ec` **P0 回归基线更新到 Windows 权威值**（老板跑 gen_baseline：000063 2025-01~2026-07 Simple5/20 top10 50万 → total_return -0.006 / 27笔 / Sharpe 0.0533 / MDD -0.1733）
- `2bce2b1` 架构整理 **P1**：WangwenGate 切割（等价替换，行为不变）
- `e63c571` 架构整理 **P1 后半**：TagRouter 最小版（震荡票跳过趋势门逻辑外移）
- `3646db0` 架构整理 **P2-1**：配置驱动装配台（PipelineConfig + from_config）
- `876b107` 架构整理 **P2-2**：registry 完善 + 标准配置模板库 + 配置驱动入口
- `e92f89f` **架构整理回退**：删 P2 配置驱动层，保留 P0 基线 + P1 闸门切割（老板拍板：不盲从 CPU，实盘优先）
- `ec756b6` 决策：代码卫生后置原则（老板拍板）——先出可上实盘的东西，方法固定后再收拾代码（DECISIONS §3.6）

## 十六、架构整理 P1：WangwenGate 切割（2026-09-02 老板+CPU+小二陈协作）

**背景**：老板要 pipeline 横切逻辑外移；CPU 设计 Gate 接口（审校后定版）；P1 只切最独立 WangwenGate，等价替换不重构执行链。
**产出**：
- `core/backtest/gates/base.py`：Gate 基类（name/exit_priority/prepare/filter_buy_candidates/should_exit；买/卖分开，market_data 可选，默认空实现）
- `core/backtest/gates/wangwen_gate.py`：WangwenGate（ww_min 进场门槛 + ww_exit 恶化退出，逻辑从 pipeline 原样搬入）
- `pipeline.py`：ww 逻辑换成调 ww_gate（__init__ 建 gate；prepare/filter/should_exit 走 gate；**调用顺序不变**）
**等价验证（WSL 双用例与 P1 前逐位一致）**：
- 海王000078 ww_min=2 → 0笔买入（无闸门50笔），一致
- 万邦德002082 ww_exit=1 → 84笔，一致
**待办**：Windows 跑回归（gen_baseline 对比）；P1 后半 TagRouter 最小版（trend_gate_split）；P2 铺开 MarketGate/TrendGate

**P1 后半 TagRouter 最小版完成**：震荡票跳过趋势门逻辑从 pipeline(_load_osc_codes) 抽到 gates/tag_router.py。
- TagRouter：prepare 加载震荡标签 + should_skip_gate(symbol,date,gate_name)（P1 只做 trend_gate；接口留扩展）
- pipeline: _osc_codes→tag_router，_trend_allows 调 should_skip_gate
- 验证：000063震荡→跳过True/000657趋势→False/非trend闸门不跳过/26只震荡集 全对
- ⚠️ WSL 缓存数据更新过（300只+复权），旧对比数字全漂（月线门+132.8%→+190.9%）——绝对数以 Windows 为准；split 方向仍对（split后收益更低=震荡票多买）

## 十七、架构整理回退决策（2026-09-02 老板给最大权限：回退到最合适状态，不盲从 CPU）

**老板判断**：CPU 远离一线，P2 配置驱动装配台是过度设计（实盘零增量；趋势门接不进配置=覆盖不到主力场景；旧脚本组装已够用）。
**回退**（git revert 876b107+3646db0，保留 P0/P1）：
- 保留：P0 回归基线（d4310ec，7 passed）+ P1 WangwenGate/TagRouter 切割（2bce2b1/e63c571，等价验证过）
- 回退：P2 配置层（registry/config/from_config/run_with_config/YAML模板/run_config_pool）全删
- 原则：**为实盘服务优先于架构优雅**；脚本=main 组装是够用的常态，不为此上框架
**待办 ⏳**：Windows 回归确认回退后仍 7 passed；精力转回实盘方向（选股逻辑/资金流主线/王文五数据覆盖）

## 09-05 收尾状态（供下个工作日承接）
- **回归验证**：Windows `python -B -m pytest tests/test_backtest_regression.py -q --cache-clear` → 7 passed（stale __pycache__ 坑：不 --cache-clear 会撞旧基线失败）
- **流水验账启动（老板 03:30）**：跑"精选15 + multi门 + 止盈30%"（2022-06-01~2026-08-27，--no-quality --pos-off --trend-gate multi --take-profit 0.3）→ 累计 +454.22%/年化 52.04%/Sharpe 1.20/最大回撤 -44.67%/交易 1652 → **老板贴了完整流水，验账进行中（价格对真实行情、qty×price、现金链式对平）**
- **DECISIONS.md 待提交改动**：§3.7 数据核对标准（老板修正：Windows 为唯一事实源、只挑数据内部不自洽）

## 待办 ⏳
- 流水验账结论（等老板贴全）
- 实盘方向三选一：①定一套实盘打法 ②王文五数据源一次性渠道 ③资金流主线榜
- DECISIONS §4.6：王文五滚动池 + 底背离反转组合测试
