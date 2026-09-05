# 开发记录 —— 2026-09-06（凌晨场，承接 09-05 流水验账）

> **一句话总结**：精选15流水账验收**全部通过**（2051 笔全量核对 0 差异）；打通 cmd 通道（WSL 直调 Windows python）——"WSL vs Windows 复现不一致"死结解开。

## 一、流水账验收结论（老板 2026-09-05 指令，今日定案 ✅）

**验收对象**：精选15 + multi门 + 止盈30%（2022-06-01~2026-08-27，--no-quality --pos-off --trend-gate multi --take-profit 0.3，50万起）完整流水。

**验收方法**：用 Windows python 复现（见 §三）→ 得到与老板逐位一致的权威流水（outputs/ledger_winpy.txt，2051 笔，与老板 ledger_full.txt diff 0 差异）→ 全量逐笔验账。

**逐项结果（2051 笔全量，非抽样）**：
| 验证项 | 结果 |
|---|---|
| 成交价 = 当日 qfq 收盘价（原始价×复权因子重建对照） | 2051 笔全一致，0 偏差 ✅ |
| 数量 = 100 整数倍（一手） | 0 违规 ✅ |
| 同股同日多个成交价（假成交特征） | 0 组 ✅ |
| 卖超（空仓卖出） | 0 笔 ✅ |
| 总资产链式重建（现金+持仓市值 vs 流水列） | 2022-08-02 / 2024-01-08 / 2026-08-26 三日分毫不差 ✅ |

**结论**：**流水为真、无假账**。累计 +483.74% / 2051 笔 / Sharpe 1.38 / MDD -31.84%（Windows 权威，已复现逐位一致）。

## 二、验账脚本（供复用）
- `scripts/dump_md_for_compare.py`：导出 SDK 加载的 OHLCV 供对比（今日建，可留可删）
- 验账逻辑：解析流水 → qfq close 对照（HTTP 原始价 × 复权因子表，bisect 同 SDK 算法）→ 数量/同日同价/卖超/资产链重建
- 资产链重建法：cash = 500000 − Σ买 + Σ卖；持仓按当日 qfq close 估值；total_asset = cash + Σ sh×close，与流水总资产列对比

## 三、cmd 通道（本次最大收获：WSL 直调 Windows python）⭐

**问题背景**：同仓库、同 stockdb、同命令，WSL 跑 2204 笔/492.86% vs Windows 2051 笔/483.74%——000063 单票逐位一致，15 票多票组合分叉（评分排序竞争对尾差敏感，"0.1% 差放大成 4 倍收益差"）。已排除：代码（E盘共享）、复权因子（同表）、成交价（1992 笔 0 差）、数据范围（同 1031 交易日）。残留差异源：SDK vs HTTP 数据细节 + pandas 3.0.5(WSL) vs 2.3.3(Windows)。

**解法（老板点拨：另一个同事能跑 cmd → 我也能）**：WSL 里直接调 Windows 的 cmd.exe 跑 Windows python，数字与老板逐位一致。

**可用口令模板**（以后复现对账默认用它，不再用 WSL venv）：
```
cmd.exe /d /c "cd /d E:\stockgate\Quant_Alpha_System && set PYTHONIOENCODING=utf-8 && python -B scripts\run_simple_pool.py <参数> > E:\stockgate\Quant_Alpha_System\outputs\xxx.txt 2>&1 & echo DONE"
```
要点：
- `cmd.exe /d /c`：/d 避免 UNC 路径报错；必须 `cd /d E:\...` 先切盘
- `set PYTHONIOENCODING=utf-8`：不加会 GBK 编码崩（emoji 🚀 无法输出到文件）
- Windows python = `E:\python\python.exe`（Python 3.13.4 / pandas 2.3.3 / numpy 2.2.6）
- 输出文件 WSL 可直接读（/mnt/e/...）
- cmd 中文输出在 WSL 显示乱码（GBK vs UTF-8 终端），不影响功能

**WSL venv `.venv-winlike`**（pandas 2.3.3+numpy 2.2.6 同 Windows 版）已建：仅开发自检参考，数字对账仍以 cmd 通道跑出的为准。

## 四、待办 / 收尾
- 清理：outputs/ledger_full.txt、ledger_wsl_winpy.txt（中间产物）；scripts/dump_md_for_compare.py 按需留
- DECISIONS §3.8 已记"Windows cmd 唯一执行台"（09-05 版）——今日证实小二陈可自跑 cmd，见 DECISIONS 最新
- git 提交：DECISIONS §3.8 + 本笔记（等老板发话）
