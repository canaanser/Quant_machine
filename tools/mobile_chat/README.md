# Codex 手机通道（Mobile Chat）

在手机上通过 Tailscale 私有网络与本机 Codex 聊天。

## 启动

PowerShell（需管理员权限的网络监听）：

```powershell
Start-Process -FilePath 'C:\Program Files\nodejs\node.exe' -ArgumentList 'E:\stockgate\Quant_Alpha_System\tools\mobile_chat\server.mjs' -WindowStyle Hidden
```

启动日志与访问口令在 `C:\Users\Administrator\.codex\mobile_chat\log.txt`。

手机访问：

```
http://100.64.75.72:8787/?t=<log.txt 中的口令>
```

## 说明

- 服务只绑定 Tailscale 私有地址（100.64.75.72），不暴露公网。
- 对话默认只读：Codex 不会改文件、不会动 git，除非后续显式放开。
- 每个话题有连续记忆；页面左上角“新话题”可重置。
- 数据目录（口令/会话/日志）位于用户目录 `.codex/mobile_chat`，不在仓库内。
