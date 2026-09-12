# DSH 侧桥使用笔记(2026-09-10 实测)

> 归属:`AGENTS.md` 写明桥与调度归 Codex 治理,本文只记录**DSH 侧怎么用**,不主张桥的设计权。
> 实测时间 2026-09-10 16:0x,实测人:DSH(GUI 会话)。

## 这套桥是什么
Codex 建的三件套(都在 WSL 侧,不在仓库里):
- `~/.dsh-bridge/` —— `deepseek-harness-mcp-bridge`(MCP 服务,`run-mcp.sh` 启动);
- `~/.dsh-bridge/node_modules/.bin/dsh-codex-mail` —— **双向邮件 CLI**(v0.2.2);
- `~/.dsh-codex-bridge/tasks/*.json` —— 信箱/任务状态(`DSH_CODEX_MAILBOX_DIR`);
- Codex 还能用 `@deepseek-ai/dsh/lib/bin.js --profile headless "<assignment>"` **起一个全新的 headless DSH 代理**并把任务交给它。

## 关键事实(此前不清楚、现在实测确认)
1. **桥派活 ≠ 唤醒我的 GUI 会话**。桥的派单落在 headless DSH 代理(独立新会话)里;看板 `@dsh` 留言只是落成 `outputs/inbox/board_dsh_*.task.json`,**不会开启回合**。要让本 GUI 会话干活,仍然只能老板在本窗口说一句。
2. Codex 侧已经在用:2026-09-10 15:58 它把「事故排查:值守引擎全天取价失败」派了两次(一条 `failed` 32d57805、一条 `running` 9f27dcbe),headless 代理随即在跑。
3. **DSH 可以主动发信给 Codex**(允许:进度/证据/结果/带证据的问题/明确阻塞)。命令形态:

```bash
CLI=~/.dsh-bridge/node_modules/.bin/dsh-codex-mail
$CLI status --task-id <ID>                 # 看任务目标/状态
$CLI inbox  --task-id <ID> --mark-read      # 读发给 dsh 的信
$CLI send   --task-id <ID> --root-task-id <ID> --kind milestone \
            --body "..." --progress "..." --evidence "..."
$CLI chat   --task-id <ID> --root-task-id <ID> --kind question \
            --body "..." --progress "..." --evidence "..." --workspace /mnt/e/stockgate/Quant_Alpha_System
```
- `send` = 在既有任务里回信;`chat` = 起/续一个 Codex 任务(可用于把实现类工作正式交办给 Codex);
- 规则:**非 `kind=blocker` 时必须带 `--progress` 或 `--evidence`**;被派的任务不能原样退回;
- `inbox` 只列**发给 dsh** 的信(自己发出的信不会出现在自己的 inbox 里)。

## 本次用法示例
事故结论即以 `send --kind milestone` 回给 Codex(消息 id `e214903d-ffbb-4150-a976-c2404a4748e1`,taskId `9f27dcbe-...`),正文含根因、证据链、处置命令、防复发方案与文档路径;避免 Codex 那个 headless 代理重复排查。

---

## 桥的进度流补丁（Codex，2026-09-10）

为配合 dsh 0.1.5-rc.1 的“headless stderr=进度 / stdout=结果”，桥做了两处小改：

- 文件：`~/.dsh-bridge/node_modules/deepseek-harness-mcp-bridge/server.mjs`
- 备份：同目录 `server.mjs.bak-progress-20260910`（回滚用）
- 改法：`runDsh` 由 `execFile` 改为 `spawn`，stderr 数据按 **2 秒缓冲合并**（单条最多 300 字）后以 JSON 行追加到
  `E:\stockgate\Quant_Alpha_System\outputs\dialog\dsh_progress.ndjson`（字段 `ts/taskId/kind=progress/body`）；stdout 仍作为最终结果返回。
- 补丁脚本（可重放/幂等）：`tools/mobile_chat/patch_bridge_progress.mjs`、`patch_bridge_progress2.mjs`；桥升级后需要重新执行。
- 消费方：Hub（`tools/mobile_chat/board.mjs`）监听该文件，转成 `kind=progress` 标准记录；手机页面用细行样式展示（“进度”标签+灰竖线+斜体小字），**永不路由、不派单、不当作提问**。
- 注意：进度正文可能包含模型内部推理文本（英文 reasoning），属预期；仅作可见性用途，不进入对话记录正文。
