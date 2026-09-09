# 一键复现环境指南（Docker / 新机器）— 2026-09-07 老板拍板

> 目的：**代码 + 基线在 GitHub，依赖 + 配置一键搞定**，换机器马上能重现工作场景。

## 分层总览：这套系统跑在哪

| 环境 | 用途 | 依赖来源 |
|---|---|---|
| **Windows 权威台**（`E:\python`） | 一切**出数字**：回测/对账/权威执行 | `requirements-win.txt` + `3rdpart_pybao/`(stockdb.pyd) + 本机 stockdb.exe |
| **Docker 镜像**（`python:3.12`） | **纯分析/研究/画图**脚本（不依赖 stockdb SDK 的） | `requirements.txt`（含全部依赖，一键装好） |
| **WSL 开发 venv** | 我（小二陈）写代码/自检 | `.venv-quant`（pandas3.0.5） |

## 一、Docker 一键复现（纯分析环境）

```bash
# 1. 拉代码
git clone git@github.com:canaanser/Quant_machine.git && cd Quant_machine

# 2. 构建（锁好依赖，一层层缓存，之后秒起）
docker build -t quant_alpha .

# 3a. 纯分析：直接进容器跑（pandas/numpy/streamlit 都齐）
docker run --rm -it quant_alpha
#     容器里就可以: python scripts/xxx.py / 分析脚本

# 3b. 要行情数据（宿主机已启动 stockdb.exe）：
docker run --rm -it --add-host=host.docker.internal:host-gateway quant_alpha
#     容器内数据层自动回退 HTTP, 连宿主 127.0.0.1:7899 → 见 core/data_loader
```

**为什么数据走 HTTP 而不在镜像里放 SDK**：`3rdpart_pybao/stockdb.pyd` 是 Windows 二进制，
Linux 容器装不上；`core/data_loader/freestockdb.py` 已内置回退（import 失败 → HTTP 连宿主）。
权威口径（SDK qfq 对账）仍只在 Windows 跑，见 `DECISIONS.md §3.8`。

## 二、新 Windows 机器（要跑权威回测）

```bash
# 1. 代码
git clone git@github.com:canaanser/Quant_machine.git
# 2. 装 3rdpart_pybao（含 stockdb.pyd）→ 跑一次 3rdpart_pybao/安装.py 即可被 import
# 3. 装依赖（权威版！）
pip install -r requirements-win.txt
# 4. 启动你自己的 stockdb（数据服务 127.0.0.1:7899）
# 5. 验证: python -B scripts/health_check.py（或跑最小回测对基线）
```

## 三、依赖锁文件说明

- `requirements.txt` → **开发/容器**（pandas 3.0.5 / numpy 2.5.2, py3.12）
- `requirements-win.txt` → **Windows 权威台**（pandas 2.3.3 / numpy 2.2.6, py3.13.4）
- 两份都是**实测跑通**的组合，别混装、别随意升版本；换版本前先跑回归
  （`tests/`，尤其 test_backtest_regression.py 锁着基线行为）

## 四、配置项（机器无关，已在 config/config.py）

- 所有数据路径都是项目相对路径（`data/...`），无硬编码 E:\ / D:\
- stockdb 服务地址 `127.0.0.1:7899` 写在 `core/data_loader/freestockdb.py`（容器里改 host 为 host.docker.internal）
- 数据文件（`data/index_store/*.db`、`data/cache/`、`reports/`）**不进 git**，各机器自己放/拉

## 五、边界（诚实说明）

- 镜像**跑不了** stockdb SDK 权威回测 —— 那是 Windows 的事（pyd 二进制 + §3.8 口径）
- 镜像**能跑**：所有只用 pandas/numpy 的分析、统计、画图、研究脚本；
  需要行情时经 HTTP 连宿主 stockdb（非权威口径，做方向性研究足够）
- 如果某天数据源换 yfinance/akshare（requirements 已含），镜像就彻底独立了
