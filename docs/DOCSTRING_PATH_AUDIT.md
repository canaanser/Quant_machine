# docstring 路径审计(2026-09-10,DSH)

> 起因:老板让修 `plugins/webread.py` 的路径 bug(自称 `core/webread.py`)。修完后我对全仓做了同类扫描。
> **总览:扫出 43 处"docstring 自称路径 ≠ 文件位置",其中只有 9 处真过时(已全部修完),另 9 处是准确的血缘说明,27 处属归档代码。**

## 一、已修(9 处,含老板点名的那个)

| 文件:行 | 原自称 | 改成 |
|---|---|---|
| `plugins/webread.py:2,5` | `core/webread.py` / `from core.webread import …` | `plugins/webread.py` / `from plugins.webread import …` |
| `core/lib/orderfile.py:2` | `(tools/toolkit/orderfile.py)` | `(core/lib/orderfile.py, 原 tools/toolkit/orderfile.py)` |
| `core/lib/quotes.py:2` | `(tools/toolkit/quotes.py)` | `(core/lib/quotes.py, 原 tools/toolkit/quotes.py)` |
| `core/lib/rdx.py:2` | `(tools/toolkit/rdx.py)` | `(core/lib/rdx.py, 原 tools/toolkit/rdx.py)` |
| `core/lib/dbfread.py:3` | `from tools.toolkit.dbfread import read_dbf` | `from core.lib.dbfread import read_dbf` |
| `core/risk/sellrules.py:2` | `(core/lib/sellrules.py)` | `(core/risk/sellrules.py, 原 core/lib/sellrules.py)` |
| `core/trade/ledger.py:2` | `core/ledger.py` | `core/trade/ledger.py (原 core/ledger.py)` |
| `core/trade/rtfeed.py:2` | `core/rtfeed.py` | `core/trade/rtfeed.py (原 core/rtfeed.py)` |
| `scripts/rt_quotes.py:3` | `数据源: core/rtfeed.py` | `数据源: core/trade/rtfeed.py` |

验证:9 个文件 `python -m py_compile` 全过;`plugins/webread.py` 按注释里的写法实测 `from plugins.webread import read_page, render` 导入成功(scrapling 可用=True);活动代码里已无旧路径残留。

## 二、判定为**不该改**(9 处,准确的血缘说明)
`core/backtest/{__init__,base,execution_mixin,pattern_mixin,pipeline}.py` 写"2026-08-26 小二陈:**core/backtest.py 拆分为包**";
`core/strategy/{__init__,alpha,base,simple}.py` 写"**拆分自 core/strategy.py**/从 core/strategy.py 拆出"。
——这些是模块拆包的历史说明,写得准确,机械替换会丢信息。**保持原样。**

## 三、归档代码,建议不动(27 处)
`experiments/**` 里的脚本是从 `scripts/` 移过来的,docstring 仍写 `scripts/xxx.py`(如 `experiments/history/probe_online_api.py:5` 等 26 个);`patch_backup/core_strategy.py:1` 是备份件。建议各加一行"已迁至 experiments/…"即可,不做路径替换。

## 四、另发现(未改,需老板/Codex 定)
- `docs/ROADMAP_MODULAR.md:21` 列的 `core/ledger.py` / `core/rtfeed.py` 等是 **2026-09-08 规划稿**里的目标结构,后来实际落成 `core/trade/…`。属历史规划件,建议加一行"结构已调整,当前见 docs/FILE_INVENTORY.md"而不是改路径。
- **功能层面没有断**:按旧路径 import 的真实代码行 grep 为空;实测 `from core.strategy import AlphaScoreStrategy, PureMACrossStrategy, SimpleStrategy`、`from core.backtest import BacktestPipeline`、`from core.trade.rtfeed import fetch` 全部 OK。

## 五、归属建议
本类问题属"代码规范"事项(AGENTS.md 分工:Codex 主审阅/规范)。DSH 已完成机械订正部分;**拆分类措辞、归档件处理、以及把"docstring 路径必须与文件一致"写进 review 规则**,建议由 Codex 定稿。

_审计方式:一次性 `os.walk` + 正则(取每个 .py 前 6 行里第一个含 `/` 的 `*.py` 声明),排除 node_modules/.git/3rdpart/outputs/data。生成时间 2026-09-10 16:5x。_
