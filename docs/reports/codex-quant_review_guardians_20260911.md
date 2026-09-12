# 独立复核意见：守护两改（codex-量化总监）

> 对象：`scripts/watch_all_dog.py`（托盘存活检查）与 `scripts/daily_artifact_check.py` + `QuantArtifactCheck`（20:50 产物新鲜度）。

## 一、watch_all_dog.py（托盘检查）

核过：心跳过期 → 拉起 duty_engine；托盘缺失 → 用计划任务 `QuantTrayOnLogon` 拉起并写看板+日志（未直接 Popen 托盘）。

- 结论：**方向正确，可用**。
- 遗留（建议 owner 修，不阻塞）：
  1. `tray_pids()` 把"查询失败"和"确实没有托盘"都返回空列表 → 查询异常时会误判并尝试拉起；建议区分 `None/空集`（同 net_guard 的写法）。
  2. 看板写入是直接 append 文件、署名 `dsh-老员工`，未走 `POST /api/post`、无去重；若拉起失败会每 5 分钟重复告警。建议改走 `/api/post` + 当日去重。
  3. `start_engine()` 用 `Popen` 直启引擎——当前由计划任务上下文运行（干净），风险低于 2026-09-10 那次；但为统一与留痕，建议同样改走计划任务。

## 二、daily_artifact_check.py / QuantArtifactCheck

核过：检查 `outputs/candidates_<当日>.json` 与 `outputs/next_plan.csv` 的 mtime ≥ 当日 20:00；不合格写日志 + 看板告警；`--dry` 不写板；只读、不重启进程。

- 结论：**方向正确，可用**。
- 遗留（建议 owner 修，不阻塞）：
  1. 看板告警同样直接 append、署名 `dsh-老员工`、无去重（同上一节第 2 条）。
  2. 只校验文件新鲜度，不校验任务结果码/日志尾部；建议顺带读 `outputs/{scan,plan}_task.log` 的最后一行结果作为证据（更早定位"文件旧但任务失败"）。
  3. 20:50 时点合适；`candidates_<date>` 按当日命名与 20:15 扫描一致，无异议。

## 三、总评

两改补齐了"引擎在跑、托盘不在"和"产物静默失败"两个盲区，**建议投用**；上面四条遗留交给 owner（dsh-老员工）按 NET 卡处理。
