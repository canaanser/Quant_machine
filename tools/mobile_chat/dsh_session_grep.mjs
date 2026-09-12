import fs from "node:fs";
import zlib from "node:zlib";

const file = process.argv[2];
if (!file) {
  console.error("usage: node dsh_session_grep.mjs <session.v3.jsonl.zstd> [keyword]");
  process.exit(1);
}
const keyword = process.argv[3] || "schedule";

const buf = fs.readFileSync(file);
const magic = Buffer.from([0x28, 0xb5, 0x2f, 0xfd]);
const offsets = [];
let idx = 0;
while (true) {
  const at = buf.indexOf(magic, idx);
  if (at < 0) break;
  offsets.push(at);
  idx = at + 1;
}
const parts = [];
for (let i = 0; i < offsets.length; i++) {
  const start = offsets[i];
  const end = i + 1 < offsets.length ? offsets[i + 1] : buf.length;
  try {
    parts.push(zlib.zstdDecompressSync(buf.subarray(start, end)).toString("utf8"));
  } catch (e) {
    // 非完整帧/不支持的帧，跳过
  }
}
const text = parts.join("\n");
const lines = text.split("\n").filter((l) => l.includes(keyword));
console.log(`frames=${offsets.length} decompressed_lines=${lines.length} matched=${lines.length} text_bytes=${text.length}`);
for (const line of lines.slice(-40)) {
  console.log("---");
  console.log(line.slice(0, 900));
}
