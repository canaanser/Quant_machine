# 开发记录 —— 2026-09-02

> **一句话总结**：趋势线过滤器实验完成（做法二/三），84池月线门、精选15多级共振最优

## 一、关键接口（今天设计/修改的）

| 接口名 | 位置 | 输入 | 输出 | 变更说明 |
|--------|------|------|------|----------|
| `detect_trendlines(df, k, touch_pct, min_touches, min_span, max_span, break_pct, max_lines)` | `core/trendline/detector.py` | OHLC DataFrame | List[dict]（type/x0/y0/x1/y1/x_end/y_end/slope/touches/touch_idx） | ✅ 新增 v3：fractal+三点确认+破位截断+去冗余 |
| `period_state_map(daily, freq, min_bars)` | `core/trendline/state.py` | 日线 OHLC | 周期末→状态 Series | ✅ 新增：无前视滚动状态表（回测 T 日只消费结束日<T 的期） |
| `rolling_period_state(...)` | `core/trendline/state.py` | 日线 OHLC | 前向填充日线 bool | ✅ 新增：绘图/展示用（回测勿用，有周内偷看风险） |
| `multi_level_score(daily, freqs, min_bars)` | `core/trendline/state.py` | 日线 OHLC | 日线 int Series(0~3) | ✅ 新增：月+周+日三级共振打分（做法三） |
| `plot_kline_with_trades(..., trendlines=None)` | `utils/kline_plotter.py` | +trendlines 参数 | plotly fig | 🔄 修改：叠加趋势线 trace（红升蓝降/实虚/触碰圆点），None 保持原行为 |
| `BacktestPipeline(..., trend_gate=None, ...)` | `core/backtest/pipeline.py` | 'week'/'month'/'multi' | 买入前过滤 final_scores | 🔄 修改：+trend_gate/trend_gate_threshold 参数 + `_precompute_trend_state`/`_trend_allows`/`_build_ohlc_frames` |
| `BacktestPipeline(..., old_sell=False, ...)` | `core/backtest/{base,pipeline}.py` + `execution_mixin.py` | bool | 跳过封控层死叉直接卖 | 🔄 修改：实验A 旧卖逻辑开关（base 透传 pipeline→execution） |
| `scripts/demo_trendline.py` | scripts/ | --tickers/--start/--end | outputs/trendline_{code}.html | ✅ 新增：趋势线可视化 demo |
| `scripts/compare_trend_gate.py` | scripts/ | --pool 84/curated | 汇总表（累计/近1年/近2年/Sharpe/回撤/交易） | ✅ 新增：过滤器对比实验入口 |
| `scripts/run_simple_pool.py --trend-gate` | scripts/ | month/week/multi + --multi-threshold | 主入口带趋势门回测 | 🔄 修改：正式固化（老板 2026-09-02 拍板） |

## 二、数据结构（今天涉及的）

| 结构 | 位置 | 说明 |
|------|------|------|
| 无新增持久表 | — | 趋势线状态**不落盘**，回测 run() 内预计算存内存 `self._trend_state/_trend_score` |
| data/info/fundamentals/ | `data/info/fundamentals/{daily,reports}/{code}.csv` | 档案 reader 数据源（此前已建，今日复用验证） |

## 三、核心文件清单（今日创建/修改）

| 文件路径 | 状态 | 说明 |
|---------|------|------|
| `core/trendline/__init__.py` `detector.py` `state.py` | 新增 | 趋势线算法 + 状态预计算模块 |
| `utils/kline_plotter.py` | 修改 | +trendlines 参数（画图跟随我们的图） |
| `core/backtest/base.py` `pipeline.py` `execution_mixin.py` | 修改 | +old_sell（实验A）+trend_gate（趋势门） |
| `scripts/run_simple_pool.py` | 修改 | +--old-sell 参数 |
| `scripts/demo_trendline.py` `compare_trend_gate.py` | 新增 | demo + 对比实验 |
| `DECISIONS.md` | 修改 | §4.7 标签/§4.8 档案/§4.9 趋势线+实验结论 固化 |
| `docs/dev_notes/` | 新增 | 本规范体系（README/INDEX/当日记录） |
| `outputs/trendline_{000063,000657,300502}.html` | 新增 | demo 图（git 已提交） |

## 四、关键数据快照（今日跑出来的数字）

| 指标 | 数值 | 说明 |
|------|------|------|
| 趋势线 demo 检测 | 000063 震荡票 2升2降 / 000657 趋势票 2升1降 | touch2%/span15~250/破位8% |
| **84池 关止损 5年** | 无门 +56.7%/0.58/-29.5% → **月线门 +132.8%/0.82/-29.5%** | 近1年 -6.1% 扭成 +38.8% |
| **精选15 关止损 5年** | 无门 +456%/1.30/-34.1% → **multi≥2 +537.5%/1.42/-36.3%** | multi Sharpe 全场最高 |
| 84池 周线门 | +100.2%/0.81/**-24.2%** | 回撤最小（保守档候选） |
| 精选15 周线门近2年 | +460.9% 但回撤 **-40.4% 全场最差** | 好票别用死板单门 |
| 精选15 月线门 | +251.2%/1.02 | 重伤（拦掉好票回调买点） |
| 关止损后精选15无门 | +392% 近2年（vs 带止损进攻档 +74.8%） | ⚠️ 止损在切利润（大发现，待细查回撤换风险） |

## 五、今日问题记录

| 问题 | 根因 | 状态 | 解决方案 |
|------|------|------|----------|
| 趋势线 0 条 | 验证过严：锚点间强制贴合+全程不破位 | ✅ 已修复 | v3：中间点不强制、破位只截断不废线 |
| 4 条几乎同一条线 | 冗余未去重 | ✅ 已修复 | 末端线值差<5% 同型只留触碰最多 |
| 斜率 -0.96 怪线 | 000657 2026 高点 113.99 后回落，真实下降线 | ✅ 属实 | 数据核对无误 |
| 周内偷看风险 | 状态在周期末才确定 | ✅ 已修复 | `s[s.index < ts]` 只消费结束日<T 的期 |
| 000063 单票周线门差 | 震荡票低位买被门拦（单票不代表池） | ✅ 已记录 | 以池为准 |
| WSL 渲染 PNG 失败 | 无头 Chrome 起不来 | 🚫 暂时废弃 | HTML 交付（Windows 浏览器打开）；kaleido 装过 |

## 六、下一步计划

1. **[P0]** ~~布林带实验~~ → 🚫 暂废（Squeeze 窄带才买两池最差，见 §九）
2. **[P0]** 趋势门固化完成：run_simple_pool.py + `--trend-gate month/multi` + `--multi-threshold`（老板 2026-09-02 拍板上传）
3. **[P1]** 门 + 止损组合测试（趋势门定风险、止损兜底；现在纯门控回撤 -24%~-40%）
4. **[P2]** 84池 月线门 vs 周线门取舍（贪 vs 稳）；旧卖(--old-sell)与趋势门叠加
5. **[P3]** DECISIONS §4.6 待办：王文五滚动池 + 底背离反转组合

## 七、关键决策记录（供后续追溯）

| 决策 | 理由 | 决策时间 |
|------|------|----------|
| 84池（普通票）→ 月线门；精选15（好票）→ multi≥2 | 牛熊不兼容 + 好票差票分治：普通票严门认错快，好票松一点让利润跑 | 2026-09-02 |
| 趋势门做成 precompute 状态表而非逐日重画 | 无前视 + 性能（84只5年每次 O(1) 查表） | 2026-09-02 |
| 废弃不删只标记 | 老板：以后不一定没用；保留供换条件复用 | 2026-09-02 |

## 八、废弃/待定区（不删，供未来检索）

| 条目 | 状态 | 结论 | 复用条件 |
|------|------|------|----------|
| 趋势线检测 v1/v2 | 🚫 废弃 | 0 条线/线过密 | v3 已取代（中间点强制贴合版） |
| 月线门用在精选15 | 🚫 暂废 | -200 点重伤 | 若实盘全是趋势票可再验 |
| 周线门用在精选15 | 🚫 暂废 | 回撤 -40.4% | 若只要近2年收益不要回撤约束 |
| kaleido PNG 渲染 | 🚫 暂废 | WSL 无头 Chrome 失败 | Windows 本地或装 chrome 后可用 |
| 单票（000063）趋势门结论 | 🚫 勿引用 | 震荡票低位买被门拦 | 单票不推广，只认池级结论 |

## 九、布林带闸实验（下午追加，2026-09-02 老板：买卖由指标定，布林带加进来）

**实现**：`core/trendline/state.py` + `bollinger_gate_state()`（无前视 rolling）；pipeline `trend_gate='boll'` 分支；compare_trend_gate.py GATES 加 'boll'。
**逻辑（知乎文方法二）**：金叉发生在带宽 ≤ 近250日 40% 分位（窄带/Squeeze 期）= 整理破位启动 → 放行；带宽宽阔期金叉（假金叉多）→ 拦截。
**⚠️ 首跑 bug**：`_trend_allows` 分支只认 ('week','month')，boll 掉到底部直接 return True（全放行）→ 结果=无门。修复：boll 并入第一分支。修后 000657 交易 217→99 真拦截。

**结果（关止损 5年，与趋势门同口径）**：
| 池 | gate | 累计 | 近1年 | 近2年 | Sharpe | 回撤 | 交易 |
|---|---|---|---|---|---|---|---|
| 84池 | 无门 | +56.7% | -6.1% | +24.5% | 0.58 | -29.5% | 909 |
| 84池 | **boll** | +39.6% | -3.0% | +26.7% | **0.40** | -39.5% | 760 |
| 84池 | multi≥2 | +70.5% | +26.1% | +52.0% | 0.76 | -30.8% | 1006 |
| 精选15 | 无门 | +456.4% | +172.7% | +392.5% | 1.30 | -34.1% | 1273 |
| 精选15 | **boll** | +177.0% | +113.0% | +250.3% | **0.89** | **-48.6%** | 585 |
| 精选15 | multi≥2 | +537.5% | +200.4% | +452.8% | 1.42 | -36.3% | 1413 |

**结论**：🚫 **Squeeze 窄带才买（boll 闸）两池都最差**——84池 Sharpe 0.40（< 无门 0.58）、精选15 收益腰斩回撤 -48.6% 全场最差。窄带拦截掉的是分散风险的有效交易，且拦后持仓集中回撤放大。**趋势线门赢、布林 Squeeze 闸输**（趋势线认"结构向上"，布林认"波动收窄"——波动收窄≠要涨，A股窄带后常继续跌）。待老板指示：是否换布林带其他用法（如带宽扩张追势/上轨压力做卖出参考）或就此打住。
