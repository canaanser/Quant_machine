import fs from "node:fs";

const DIALOG = "/mnt/e/stockgate/Quant_Alpha_System/outputs/dialog/dialog.ndjson";
const PROGRESS = "/mnt/e/stockgate/Quant_Alpha_System/outputs/dialog/dsh_progress.ndjson";
const STATE = "/mnt/c/Users/Administrator/.codex/mobile_chat/state.json";

const keep = fs
  .readFileSync(DIALOG, "utf8")
  .split("\n")
  .filter((l) => {
    if (!l.trim()) return false;
    try {
      return JSON.parse(l).kind !== "progress";
    } catch {
      return true;
    }
  });
fs.writeFileSync(DIALOG, keep.join("\n") + "\n");
fs.writeFileSync(PROGRESS, "");

const st = JSON.parse(fs.readFileSync(STATE, "utf8"));
st.progressOffset = 0;
fs.writeFileSync(STATE, JSON.stringify(st, null, 2));
console.log("reset done, dialog_lines=" + keep.length);
