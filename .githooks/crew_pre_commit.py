"""提交闸 · pre-commit（2026-09-13 老板指示落地）

拦两类今晚真出过的事故：
  ① **署名不是名册里的看板名**（今晚：提权提交 → Git 用默认身份 `canaanser <632106943@qq.com>`
     → 门禁判"署名不合规"、白跑一轮）；
  ② **在别人的分支上提交**（今晚：共享工作树被切到 `feature/trd-003-tail-exec-fix`，
     我在没看分支的情况下提交，落到量化线的分支上）。

判据（都从真源现算，不写死）：
  · 名册 = `outputs/dialog/agents.json`（`label` = 看板名，`slug` = 工号）；
  · 署名合规 = `user.name` ∈ 名册 label（或 `老板`）**且** `user.email` == `<该线 slug>@agents.canaanser.local`；
  · 分支归属 = 分支名前缀 → 拥有者：`trd-`→codex-量化总监、`hub-`→codex-看板编辑、
    `plt-`→codex-总监/老板、`kit-`→codex-套件、`net-`/`dat-`→dsh-老员工。
    分支带了某个前缀、而提交者不是该拥有者 → **拒绝**（先确认分支再提交）。

绕过：`CREW_HOOK_BYPASS=1`（留痕靠自觉：老板本人或"先止血"）。
自测：本文件支持 `CREW_TEST_NAME` / `CREW_TEST_EMAIL` / `CREW_TEST_BRANCH` 覆盖，便于直接跑。
"""
import io
import json
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROSTER = os.path.join(REPO, "outputs", "dialog", "agents.json")
DOMAIN = "@agents.canaanser.local"

# 分支前缀 → 拥有者（看板名）；这是"任务前缀归谁"的镜像，改这里即可
PREFIX_OWNER = {
    "trd-": ["codex-量化总监"],
    "hub-": ["codex-看板编辑"],
    "plt-": ["codex-总监", "老板"],
    "kit-": ["codex-套件"],
    "net-": ["dsh-老员工"],
    "dat-": ["dsh-老员工"],
}


def git(*args, default=""):
    try:
        return subprocess.run(["git"] + list(args), cwd=REPO, capture_output=True, text=True,
                              encoding="utf-8", errors="replace").stdout.strip()
    except Exception:
        return default


def load_roster():
    try:
        with io.open(ROSTER, encoding="utf-8") as f:
            agents = (json.load(f) or {}).get("agents") or {}
    except Exception:
        return {}
    out = {}
    for label, meta in agents.items():
        slug = str((meta or {}).get("slug") or "").strip()
        if slug:
            out[str(label).strip()] = slug
    return out


def fail(lines):
    sys.stderr.write("\n".join(lines) + "\n")
    sys.exit(1)


def main():
    if str(os.environ.get("CREW_HOOK_BYPASS") or "").strip() == "1":
        sys.stderr.write("[提交闸] 已按 CREW_HOOK_BYPASS=1 放行（请留痕：谁/为什么）。\n")
        return

    name = (os.environ.get("CREW_TEST_NAME") or git("config", "user.name")).strip()
    email = (os.environ.get("CREW_TEST_EMAIL") or git("config", "user.email")).strip()
    branch = (os.environ.get("CREW_TEST_BRANCH") or git("rev-parse", "--abbrev-ref", "HEAD")).strip()
    roster = load_roster()
    head = "[提交闸] 当前分支 = %s ｜ 提交者 = %s <%s>\n" % (branch or "?", name or "?", email or "?")

    # ① 署名：必须是名册里的看板名 + 对应工号邮箱
    if name not in roster and name != "老板":
        fail([
            head.rstrip(),
            "[X] 拒提交：`user.name` = %r 不在名册里（名册 = outputs/dialog/agents.json）。" % name,
            "  红线：署名一律实名看板名。修法（一行）：",
            '    git config user.name "codex-量化总监" && git config user.email "codex-quant@agents.canaanser.local"',
            "  （把两个值换成你自己的看板名/工号；工号见名册。）",
            "  仅老板本人或紧急止血可绕过：CREW_HOOK_BYPASS=1 git commit ...",
        ])
    if name == "老板":
        return
    expect = roster.get(name, "") + DOMAIN
    if email != expect:
        fail([
            head.rstrip(),
            "[X] 拒提交：`user.email` = %r，应为 %r（看板名 %s 对应的工号邮箱）。" % (email, expect, name),
            '  修法：git config user.email "%s"' % expect,
        ])

    # ② 分支归属：带别人前缀的分支不许提交
    low = branch.lower()
    for prefix, owners in PREFIX_OWNER.items():
        if ("/" + prefix) in low or low.startswith(prefix):
            if name not in owners and name != "老板":
                fail([
                    head.rstrip(),
                    "[X] 拒提交：这个分支（%s）按前缀 `%s` 归 %s，而你是 %s。" % (branch, prefix, "/".join(owners), name),
                    "  今晚的教训（L27 邻案）：共享工作树被切到别人的分支时，提交会落到**别人的分支**上。",
                    "  先确认：git branch --show-current；不是你的分支就停手并投对方信箱一行。",
                    "  仅老板本人或紧急止血可绕过：CREW_HOOK_BYPASS=1 git commit ...",
                ])
    sys.stderr.write(head)


if __name__ == "__main__":
    main()
