import fs from "node:fs";

const P = "/home/lgy/.dsh-bridge/node_modules/deepseek-harness-mcp-bridge/server.mjs";
const BAK = P + ".bak-progress-20260910";

let s = fs.readFileSync(P, "utf8");
if (s.includes("DSH_PROGRESS_FILE")) {
  console.log("ALREADY_PATCHED");
  process.exit(0);
}
if (!fs.existsSync(BAK)) fs.copyFileSync(P, BAK);

const oldImport =
  "import { mkdir, readFile, readdir, rename, stat, unlink, writeFile } from 'node:fs/promises';";
const newImport =
  "import { appendFile, mkdir, readFile, readdir, rename, stat, unlink, writeFile } from 'node:fs/promises';";
if (!s.includes(oldImport)) throw new Error("import line not found");
s = s.replace(oldImport, newImport);

const start = s.indexOf("function runDsh(prompt");
if (start < 0) throw new Error("runDsh not found");
const endMarker = s.indexOf("\n}\n", start);
if (endMarker < 0) throw new Error("runDsh end not found");

const newRun = `function runDsh(prompt, { cwd, signal, taskId }) {
  return new Promise((accept, reject) => {
    const child = spawn(dshBin, ['--profile', 'headless', prompt], {
      cwd,
      signal,
      env: {
        ...process.env,
        PATH: \`\${dirname(process.execPath)}\${delimiter}\${process.env.PATH || ''}\`,
      },
    });
    let stdout = '';
    let stderr = '';
    let settled = false;
    const progressFile = process.env.DSH_PROGRESS_FILE || '/mnt/e/stockgate/Quant_Alpha_System/outputs/dialog/dsh_progress.ndjson';
    const tee = (chunk) => {
      if (!taskId) return;
      const ts = new Date().toISOString();
      const lines = String(chunk).split(/\\r?\\n/).map((x) => x.trim()).filter(Boolean);
      if (!lines.length) return;
      const payload = lines.map((body) => JSON.stringify({ ts, taskId, kind: 'progress', body }) + '\\n').join('');
      appendFile(progressFile, payload).catch(() => {});
    };
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { const t = d.toString(); stderr += t; tee(t); });
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      try { child.kill('SIGKILL'); } catch {}
      const err = new Error('dsh timed out after ' + timeoutMs + 'ms');
      err.stdout = stdout; err.stderr = stderr; reject(err);
    }, timeoutMs);
    child.on('error', (error) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      error.stdout = stdout; error.stderr = stderr; reject(error);
    });
    child.on('close', (code, sig) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      activeDshChildren.delete(child);
      if (code === 0) { accept({ stdout, stderr }); return; }
      const err = new Error('dsh exited code=' + code + ' signal=' + (sig || ''));
      err.stdout = stdout; err.stderr = stderr; reject(err);
    });
    activeDshChildren.add(child);
  });
}`;
s = s.slice(0, start) + newRun + "\n" + s.slice(endMarker + 3);

const oldCall = "const { stdout, stderr } = await runDsh(prompt, { cwd, signal });";
if (!s.includes(oldCall)) throw new Error("call site not found");
s = s.replace(oldCall, "const { stdout, stderr } = await runDsh(prompt, { cwd, signal, taskId });");

fs.writeFileSync(P, s);
console.log("PATCHED");
