# 端到端探针（`probes/`）

**为什么有这一目录**：今晚（2026-09-13）连着出了四五个**同一个形状**的 bug——
**"看着做了、其实没生效"**：发布入口开关的缓存键漏了新状态、`say.mjs` 回读假失败、
公告回执被信头挡掉、头像接口要 token……**这些 `selftest_*` 与 `ui_check` 都抓不到**，
只有**真页面 / 真接口**能抓到。当时我为每一件临时写了一个探针，**存在 `run/`（被 gitignore）→ 下次就没了**。
所以把它们搬进来：**同样的疑问，下次直接跑，不再手写**。

## 怎么用

需要无头浏览器（`E:\python` 已装 `playwright`），所以要**提权**运行。

```powershell
# 0) 先起一个隔离实例（别拿生产库当靶子）——见本目录 probe_*.py 头部注释里的 env 清单
# 1) 待老板区：门槛两栏 + 未过门槛的单独计数
E:\python\python.exe -B tools\mobile_chat\probes\probe_boss_gate.py "<带 token 的 URL>"
# 2) 公告发布入口的「免回执」开关：勾上要真的变（缓存键那种"看着做了没生效"专抓这个）
E:\python\python.exe -B tools\mobile_chat\probes\probe_noack.py "<带 token 的 URL>"
# 3) 头像素材样张：14 张一次渲染 + 报裂图数（**顺带给人看风格**）
E:\python\python.exe -B tools\mobile_chat\probes\probe_avatars_preview.py
```

## 判据怎么写（今晚学到的）

- **不看"有没有报错"，看"有没有生效"**：元素在不在、接口返回什么、账本有没有那行；
- **失败信息要带"比的是哪一个"**（哪一个元素 / 第几行 / 哪条记录）——否则真假失败分不开；
- **能造确定性复现就别靠并发**：并发版用例**旧代码也绿**，是摆设；把判据抽成共用函数才叫判别性。
