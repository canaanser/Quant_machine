import glob
import json
import os

ROOT = os.path.expanduser(r"~\.codex\sessions")

LABELS = {
    "01a0877b-284f-7480-80a1-c957063b9198": "桌面主线程(当前对话)",
    "01a0882c-24c6-71e2-a5c5-9edbf635c1f5": "看板自动回复线程",
    "01a0881d-9565-7142-95fa-940413769982": "手机聊天页线程",
}


def main():
    rows = []
    for path in glob.glob(os.path.join(ROOT, "**", "*.jsonl"), recursive=True):
        try:
            if os.path.getsize(path) < 1000:
                continue
        except OSError:
            continue
        turns = 0
        inp = cached = out = reasoning = 0
        thread = None
        first = last = None
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if '"token_usage_record"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                p = obj.get("payload") or {}
                u = p.get("usage") or {}
                inp += int(u.get("input_tokens") or 0)
                cached += int(u.get("cached_input_tokens") or 0)
                out += int(u.get("output_tokens") or 0)
                reasoning += int(u.get("reasoning_output_tokens") or 0)
                turns += 1
                thread = p.get("thread_id") or thread
                ts = obj.get("timestamp")
                first = first or ts
                last = ts or last
        if turns:
            rows.append(
                {
                    "thread": thread or os.path.basename(path),
                    "turns": turns,
                    "inp": inp,
                    "cached": cached,
                    "uncached": inp - cached,
                    "out": out,
                    "reasoning": reasoning,
                    "total": inp + out,
                    "avg_in": inp // max(turns, 1),
                    "first": first,
                    "last": last,
                    "path": path,
                }
            )

    rows.sort(key=lambda r: -r["total"])
    print(f"{'会话':<28}{'回合':>6}{'输入':>12}{'其中缓存':>12}{'输出':>9}{'合计':>12}{'平均输入/回合':>14}")
    for r in rows:
        label = LABELS.get(r["thread"], r["thread"][:8])
        print(
            f"{label:<28}{r['turns']:>6}{r['inp']:>12,}{r['cached']:>12,}{r['out']:>9,}{r['total']:>12,}{r['avg_in']:>14,}"
        )

    groups = {}
    for r in rows:
        label = LABELS.get(r["thread"], "其他会话")
        g = groups.setdefault(label, {"turns": 0, "inp": 0, "cached": 0, "out": 0, "total": 0, "weighted": 0})
        g["turns"] += r["turns"]
        g["inp"] += r["inp"]
        g["cached"] += r["cached"]
        g["out"] += r["out"]
        g["total"] += r["total"]
        g["weighted"] += (r["inp"] - r["cached"]) + int(r["cached"] * 0.1) + r["out"] * 3
    print("\n按类别汇总（计费权重 ≈ 未缓存输入 + 0.1×缓存输入 + 3×输出）：")
    grand_w = sum(g["weighted"] for g in groups.values()) or 1
    for label, g in sorted(groups.items(), key=lambda kv: -kv[1]["weighted"]):
        share = g["weighted"] / grand_w * 100
        print(
            f"{label:<28} 权重 {g['weighted']:>12,}  ({share:5.1f}%)  原始合计 {g['total']:>12,}  回合 {g['turns']:>4}  平均输入/回合 {g['inp']//max(g['turns'],1):>9,}"
        )


if __name__ == "__main__":
    main()
