# 数据架构: 本地 A股数据(D:\a股数据) ↔ 项目(E:\stockgate\Quant_Alpha_System) 的关系与嫁接

> 写给 Codex 的数据链路事实清单(2026-09-10)。

## 一、两侧是什么
**数据侧(独立于项目代码, 一套自建免费行情服务, 老板叫"低配A股数据")**
- 常驻服务: `D:\a股数据\stockdb\stockdb.exe`, 监听本机 **127.0.0.1:7899**。
- 数据仓库: `D:\a股数据\stockdb\data`、`data1`(RocksDB .ldb + .sync_manifest 元数据)。
- 当日收盘入库: `D:\a股数据\stockdb\数据更新.exe`(数据源 `sync_url.txt` → https://ah.123128.xyz)。
  机制(老板拍板): 启动 → 等 ~10 分钟 → **把它关掉 → 数据定稿可读**。计划任务 `QuantDataSync` 每交易日 20:00 用 `scripts/run_data_sync.py` 包装执行。
- 使用顺序(官方说明): 先"数据更新.exe"(或 -run <time>) → 再启动 stockdb.exe。

**项目侧(E:\stockgate\Quant_Alpha_System)**
- Python 量化系统: core(策略/风控/交易/公共库)、scripts(扫描/计划/研究)、duty(值守引擎)、self_api.py(根, 对外冻结接口)、outputs(台账/计划/日志)、docs(规范)。
- 数据消费封装(嫁接点就在这两层):
  - `core/lib/rdx.py` — 原生 rd 绑定(3rdpart_pybao 的 stockdb pyd), 历史/当日K、前缀全市场、QueryResult 网格(keys/vals)解析; day_rows 兼容 list/dict/QueryResult。
  - `core/data_loader/freestockdb.py` — 走 **HTTP JSON**: `http://127.0.0.1:7899/?cmd=get&t=<expr>&json=1`; fetch_daily_qfq_single 逐只 qfq 日K(1 请求/只)。
  - `scripts/*` 与研究脚本常用 HTTP JSON 直接取: 日k:code:* ; 分钟k:code:YYYYMMDD* → 当日 242 根(list of [key, dict])。
- 实时价(盘中)另有通道: `core/lib/quotes.py`(腾讯 qt.gtimg, 502 需重试) — 与 7899 并存: 7899 管历史/收盘/分钟, 腾讯管盘中即时价。

## 二、嫁接关系(一句话)
**7899 是数据服务对外端口; 项目不是数据的所有者, 是"消费者+调度者"**: 项目通过①原生 rd(绑定)与②HTTP JSON 两种协议消费; 项目负责在 20:00 调度数据更新.exe 把当日收盘写进 D:\a股数据, 盘后扫描/生成计划在 20:15/20:40 用 7899 数据; 次日交易时段引擎用腾讯实时价执行(14:44 尾盘)。

## 三、关键代码入口索引
| 用途 | 入口 |
|---|---|
| 原生 rd 封装 | core/lib/rdx.py: get/day_rows/universe |
| HTTP JSON 取数 | scripts 内 http_json(urllib, expr=日k:code:* 等) |
| 单只 qfq 历史 | core.data_loader.freestockdb.fetch_daily_qfq_single |
| 盘中实时 | core.lib.quotes.live_px(腾讯) |
| 数据同步任务 | scripts/run_data_sync.py(启动exe→10min→关) |
| 收盘归档读资金 | core/lib/emq_arch.py(东财 .emgm3 归档, 与7899不同源) |
| 做T分钟样本 | outputs/min_samples/*.csv(7899 HTTP 抓取缓存) |

## 四、注意(Codex 动数据/调度时)
- 不要重复拉起 stockdb(已有计划任务/登录自启 QuantDbOnLogon)。
- 数据更新.exe 不会自退, 必须"到点关闭"才定稿(run_data_sync 已处理)。
- 7899 QueryResult 非普通 list: keys()=[[key,cols],...] 或单行 keys/vals 拼 dict; 迭代会出列名, 勿当 list 遍历。
- 分钟时间戳 14 位(YYYYMMDDHHMMSS), 取日需 //1000000。
- 单文件/单码真源改动登记与审计按 AGENT_SPLIT.md。
