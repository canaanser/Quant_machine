import fs from "node:fs";

const DIR = "/home/lgy/.dsh/profiles/web";
const PATCH = DIR + "/cordis.patch.yml";
const MARK = "# schedule overlay (Codex 2026-09-10)";
const BODY = `${MARK}
# 启用 dsh 自带的定时提醒（same-session follow-up 唤醒）
- insert:
    - id: schedule
      name: '@deepseek-ai/dsh-schedule'
    - id: schedule-ui
      name: '@deepseek-ai/dsh-client-ui-schedule'
`;

const mode = process.argv[2] || "apply";

if (mode === "apply") {
  if (fs.existsSync(PATCH)) {
    const cur = fs.readFileSync(PATCH, "utf8");
    if (cur.includes("dsh-schedule")) {
      console.log("ALREADY_APPLIED");
      process.exit(0);
    }
    fs.copyFileSync(PATCH, PATCH + ".bak-schedule-" + Date.now());
  }
  fs.writeFileSync(PATCH, BODY);
  console.log("APPLIED");
} else if (mode === "revert") {
  if (fs.existsSync(PATCH) && fs.readFileSync(PATCH, "utf8").includes(MARK)) {
    fs.unlinkSync(PATCH);
    console.log("REVERTED (removed overlay)");
  } else {
    console.log("NOT_OURS_OR_MISSING");
  }
} else {
  console.log("usage: apply|revert");
}
