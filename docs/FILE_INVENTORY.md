# FILE_INVENTORY — 项目文件地图 (审计底图)

> 统计口径: 源文件数 = 各目录下普通文件, **不含 __pycache__/.git/node_modules**。
> 统计日期: 2026-09-10 04:1x(快照; 数量以最新目录为准, 偏差±1属统计瞬间临时文件, 无关紧要)。
> 三档标注: **在用 / 待机(历史, 不删只标记) / 可清(候选清单, 删除前须登记并经 Codex/老板确认)**。

| 文件夹 | 文件数 | 是什么 | 状态 |
|---|---|---|---|
| `core/` | 73 | 内核: risk/trade/lib/data_loader/backtest/strategy/profile; sellrules/ledger/orderfile/rdx/emq_arch 真源 | **在用** |
| `duty/` | 9 | 值守引擎 duty_engine.py/schedule.yaml/tray_guard/README | **在用** |
| `self_api.py` | 1(根) | 引擎→系统冻结接口 | **在用** |
| `scripts/` | 84 | 值守链在用: gen/compose/close_check/run_data_sync/watch 系/intraday/td/emq_pull; 其余历史实验 | 在用(值守链) / 其余**待机** |
| `outputs/` | 251 | 台账/计划/订单/日志/min_samples/候选缓存 | **在用(落盘)** |
| `docs/` | 22 | 规范/日报/交接(dev_notes/AGENT_SPLIT/TO_CODEX_BRIDGE/DATA_ARCH/STATE_ANCHOR/本文件) | **在用** |
| `data/` | 709 | 股票列表/用户数据/raw 备份(非代码) | 在用数据(细节 Codex 深看) |
| `tools/` | 197 | 运维/一次性: start_stockdb.ps1、create_watch_tasks.bat(在用); 历史 `_` 探针 | 在用(少数) / 探针**可清候选** |
| `experiments/` | 62 | 按日策略实验/订单复盘 | **待机**(参考) |
| `structure_engine/` | 48 | 自研形态/结构扫描引擎 | 待机(非值守主链) |
| `3rdpart_pybao/` | 18 | free-stockdb SDK 绑定(7899 原生 rd) | **勿改**(依赖) |
| `3rdpart_nssm/` | 36 | 第三方 nssm 下载(未启用) | **待机** |
| `tests/` | 25 | 测试 | 待机/维护 |
| `patch_backup/` | 7 | 架构重构补丁备份 | **待机** |
| `参考/` | 4 | 外部设计书 | **待机** |
| `selection/` | 4 | 选股实验 chip_dip | 待机 |
| `config/` | 3 | 配置 | 在用/待机 |
| `Stream/` | 3 | 临时 staging/snapshots | 待机/临时 |
| `plugins/` `logs/` | 各2 | 插件/日志 | 待机(细节 Codex 看) |
| `utils/` `views/`(及旧 core 删除项) | 已在 git 标记删除 | 旧架构清理 | **可清候选**(已删登记于工作区, 未提交) |

## 说明
- "在用"核心链: core + duty + self_api.py + scripts 值守链 + outputs + docs。
- "待机": 历史/研究资产, 按老板规矩**不删只标记**。
- "可清"= 候选清单, **删除前须登记并经 Codex/老板确认**; 本清单不构成删除授权。
- 新会话/Codex 靠本文件快速定位, 少整读。
