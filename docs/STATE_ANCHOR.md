# 状态锚点 (2026-09-10 01:5x, 给新会话快速接入用)

> 用法: 新对话第一句贴本文件前 20 行要点, 或直接说"读 docs/STATE_ANCHOR.md 继续"。
> 完整锚点集按 docs/dev_notes/README.md §0: DECISIONS §3.8/3.9 + 最新日报待办。

## 现在是什么
双线模拟盘(全仿真,不碰真金)+ 值守体系已跑通 + 与 Codex 双 agent 协作刚定协议。

## 关键事实(新会话必读)
- 项目:`E:\stockgate\Quant_Alpha_System`(WSL 视角 /mnt/e/...),**有 git + GitHub 远程(canaanser/Quant_machine),但 9/6 之后改动全部未提交;老板已令:git 现在一律不动,等安排**(分支/提交规则他再定;当时我误把"切分支"当文档,做错)。
- 值守:`duty_engine.py` 常驻(登录自启+看门狗+（watch_bridge/唤醒调度 归 Codex 管理, DSH 不再自管）。托盘/面板已定稿(白版)。
- 账户:账1 组合=`a0de4b75`(14:44 尾盘,6只等权,next_plan 现=卖3买2);账2 做T学习=`5e3d5c21`(资金20万,文件单走 `C:\emq\日内分钟`,回报 downfiles/5e3d)。
- 9/10 计划:14:44 组合卖3买2;账2 建仓 8 只草案=outputs/plan2_build_20260910.csv(云南锗业/菲利华/华工/星网锐捷/昆仑万维/行云/兴森/扬杰,~15.2万,留~4.8万);开盘先100股连通测试(确认 C:\emq\日内分钟 被终端扫单)。
- 做T研究(线2):83只财报池=outputs/pool83.json;分钟样本 outputs/min_samples;机会统计 intraday_stats.txt;规则a VWAP底仓T三档结果 td_study.txt(带费,未加滑点/整手/回补纪律,待改版)。
- 成本纪律:上下文长=贵;少整读、输出看摘要;自动轮 blocked 防空转;对话太长→开新会话贴本锚点。

## 分工/待办
- AGENT_SPLIT.md 已建(DSH快/Codex稳;真源互不踩;inbox 消息桥 outputs/inbox)。
- Codex 待定:它要仓库路径(给 E:\stockgate...非 git 前提已纠正)+ dsh 位置(WSL);桥 deepseek-harness-codex-bridge 选型→建议先只读审计或自研消息盒(未动)。
- 老板待拍:git 怎么处理;账户2扫单目录确认;是否新开会话。
- 下一步(盘中):9:20桥醒→开盘检查两条线→14:44观察组合执行→账2建仓(含连通)→15:08收盘复盘写日报。
