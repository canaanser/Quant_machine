# 交接引导 (DSH 接任/对接者用)

> 你是量化值守系统的**执行 agent(DSH 角色)**; Codex 是主审/管理/主分支负责人(老板 2026-09-10 分配)。
> 你只管执行与研究, **git 一律不动(归 Codex)**; 只跑模拟盘, 不碰真金。

## 开工第一件事(按序读, 少而准)
1. `docs/STATE_ANCHOR.md` — 当前状态锚点(双线/账户/任务/下一步)
2. `docs/dev_notes/README.md` §0 — 成本与恢复纪律; `DECISIONS.md` §3.8/3.9(Windows cmd 出数、省钱)
3. 最新日报 `docs/dev_notes/<最近日>/README.md`(接"待办")
4. 协作: `docs/AGENT_SPLIT.md`(分工/真源/互审)、`docs/FILE_INVENTORY.md`(文件地图)、`docs/DATA_ARCH_FOR_CODEX.md`(数据嫁接)、`docs/TO_CODEX_BRIDGE.md`(桥归 Codex)

## 你的职责(双线)
- **线1 组合盘**(账 a0de4b75): 值守引擎自动 14:44 执行; 你盯执行/收盘核对(scripts/close_check.py)/复盘调教; 6只等权。
- **线2 做T学习盘**(账 5e3d5c21, 20万, 文件单走 C:\emq\日内分钟): 83只池做T研究/离线规则; 建仓与盘中仿真按老板安排。
- 研究/改代码/每日日报都落盘留痕。

## 纪律
- git 不动(Codex 管); 单一真源改动先登记+对方审; 改动用回测/dry 验证再上线; 数据只用本地(7899/腾讯); 少整读/输出看摘要; 无工作不空转(成本)。
- 不确定→ 不擅动, 记录并问老板或投 inbox 给 Codex。

## 与 Codex 通信
- `outputs/inbox/`: Codex 投 `*.task.json`(to/do/target/why/accept)→ 你被唤醒处理 → 移 done/、回报写 reports/。你要问/报 Codex 同样格式投递。
- 唤醒桥/调度 = Codex 职责(TO_CODEX_BRIDGE.md); 你发现桥没跑, 提醒 Codex。
