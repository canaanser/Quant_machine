# barber-mini · 理发师接单/排队小程序（微信云开发）

> 契约见 `docs/reports/PLT-009_barber_kickoff.md`（本仓 `docs/`）。**改契约要先改那份，再改代码。**

## 目录

```
projects/barber-mini/
  miniprogram/            小程序端（页面/组件/工具）
  cloudfunctions/         云函数（唯一写入口）
  shared/                 两端共用的纯逻辑（状态机/优先级/槽位）——**唯一真源**
  tests/                  node --test 单测（无网络、无云环境也能跑）
  project.config.json     开发者工具工程配置
```

## 跑测试（不需要微信环境）

```
cd projects/barber-mini
node --test          # 推荐：完全不过 PowerShell/npm
```

> ⚠️ **Windows 上别直接敲 `npm test`**：PowerShell 的脚本执行策略会挡 `npm.ps1`
> （报 `UnauthorizedAccess / about_Execution_Policies`）。两条替代：
> ① `npm.cmd test`（`.cmd` 不受该策略限制）；② 直接 `node --test`（连 npm 都不用）。
> 想一劳永逸：`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`（**不需要管理员**）。

## 三条硬约束（违反即打回）

1. 客户端**不直写** `orders`/`barbers`；写一律走云函数 `orderCreate` / `orderTransition` / `barberStatusSet`。
2. 状态机、优先级、槽位计算**只允许一份实现**（`shared/`），云函数与小程序都 import 它。
3. 迁移必须**幂等**（带 `fromStatus` + `expectedUpdatedAt`），非法迁移**拒并留痕**。
