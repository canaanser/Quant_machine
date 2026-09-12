import fs from "node:fs";

const P = "/home/lgy/.dsh-bridge/node_modules/deepseek-harness-mcp-bridge/server.mjs";

let s = fs.readFileSync(P, "utf8");
if (s.includes("DSH_PROGRESS_BUFFERED")) {
  console.log("ALREADY_BUFFERED");
  process.exit(0);
}

const start = s.indexOf("function runDsh(prompt");
if (start < 0) throw new Error("runDsh not found");
const endMarker = s.indexOf("\n}\n", start);
if (endMarker < 0) throw new Error("runDsh end not found");

const newRun = `function runDsh(prompt, { cwd, signal, taskId }) {
  // DSH_PROGRESS_BUFFERED: stderr 是逐 token 流, 这里按 2 秒缓冲合并成可读进度行
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
    let buf = '';
    let flushTimer = null;
    const flush = () => {
      flushTimer = null;
      const text = buf.replace(/\\s+/g, ' ').trim();
      buf = '';
      if (!text || !taskId) return;
      const ts = new Date().toISOString();
      const body = text.slice(0, 300);
      appendFile(progressFile, JSON.stringify({ ts, taskId, kind: 'progress', body }) + '\\n').catch(() => {});
    };
    const tee = (chunk) => {
      if (!taskId) return;
      buf += String(chunk);
      if (!flushTimer) flushTimer = setTimeout(flush, 2000);
    };
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { const t = d.toString(); stderr += t; tee(t); });
    const finish = () => {
      if (flushTimer) clearTimeout(flushTimer);
      flush();
    };
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      try { child.kill('SIGKILL'); } catch {}
      finish();
      const err = new Error('dsh timed out after ' + timeoutMs + 'ms');
      err.stdout = stdout; err.stderr = stderr; reject(err);
    }, timeoutMs);
    child.on('error', (error) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      finish();
      error.stdout = stdout; error.stderr = stderr; reject(error);
    });
    child.on('close', (code, sig) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      finish();
      activeDshChildren.delete(child);
      if (code === 0) { accept({ stdout, stderr }); return; }
      const err = new Error('dsh exited code=' + code + ' signal=' + (sig || ''));
      err.stdout = stdout; err.stderr = stderr; reject(err);
    });
    activeDshChildren.add(child);
  });
}`;

s = s.slice(0, start) + newRun + "\n" + s.slice(endMarker + 3);
fs.writeFileSync(P, s);
console.log("PATCHED_BUFFERED");
