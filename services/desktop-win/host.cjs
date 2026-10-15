'use strict';
// One long-lived PowerShell helper per MCP session. The helper compiles its Add-Type block
// once at startup and then answers NDJSON requests on stdin, so a click never pays for a new
// process or a new C# compilation. Spawned lazily: tools/list must work before any PowerShell
// is needed.
const path = require('node:path'), crypto = require('node:crypto');

class HelperError extends Error {
  constructor(message, code) {
    super(message);
    this.name = 'HelperError';
    this.code = code || 'helper';
  }
}

const DEFAULT_TIMEOUT = 20000, STDERR_KEEP = 4096;

class HelperHost {
  constructor(options = {}) {
    this.script = options.script || path.join(__dirname, 'helper.ps1');
    this.command = options.command || (process.platform === 'win32' ? 'powershell.exe' : 'powershell');
    this.args = options.args || ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', this.script];
    this.env = options.env;
    this.cwd = options.cwd;
    this.timeout = options.timeout || DEFAULT_TIMEOUT;
    this.spawn = options.spawn || require('node:child_process').spawn;
    this.child = null;
    this.pending = new Map();
    this.buffer = '';
    this.stderr = '';
  }

  get alive() { return this.child !== null && this.child.exitCode === null && !this.child.killed; }

  start() {
    if (this.child) return this.child;
    const child = this.spawn(this.command, this.args, { cwd: this.cwd, env: this.env, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
    this.child = child;
    this.buffer = '';
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', chunk => this.consume(chunk));
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', chunk => { this.stderr = (this.stderr + chunk).slice(-STDERR_KEEP); });
    child.on('error', error => this.fail('The PowerShell helper could not start: ' + error.message));
    child.on('close', code => this.fail('The PowerShell helper exited with code ' + code + '.'));
    return child;
  }

  consume(chunk) {
    this.buffer += chunk;
    for (;;) {
      const index = this.buffer.indexOf('\n');
      if (index < 0) return;
      const line = this.buffer.slice(0, index).trim();
      this.buffer = this.buffer.slice(index + 1);
      if (!line) continue;
      let message = null;
      try { message = JSON.parse(line); } catch { this.stderr = (this.stderr + '\n' + line).slice(-STDERR_KEEP); continue; }
      const entry = this.pending.get(message.id);
      if (!entry) continue;
      this.pending.delete(message.id);
      clearTimeout(entry.timer);
      if (message.ok) entry.resolve(message.data ?? {});
      else entry.reject(new HelperError(this.describe(message), message.code || 'helper'));
    }
  }

  describe(message) {
    return String(message.error || 'The PowerShell helper failed.') + (message.hint ? '\n' + message.hint : '') + this.tail();
  }

  tail() {
    const detail = this.stderr.trim();
    return detail ? '\nPowerShell: ' + detail.split('\n').slice(-4).join('\n') : '';
  }

  fail(reason) {
    const error = new HelperError(reason + this.tail(), 'helper-exited');
    for (const [, entry] of this.pending) { clearTimeout(entry.timer); entry.reject(error); }
    this.pending.clear();
    this.child = null;
  }

  request(op, args = {}) {
    const child = this.start();
    const id = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new HelperError('The Windows desktop helper timed out after ' + this.timeout + ' ms on ' + op + '.', 'timeout'));
      }, args.timeout || this.timeout);
      timer.unref?.();
      this.pending.set(id, { resolve, reject, timer });
      child.stdin.write(JSON.stringify({ id, op, args }) + '\n', error => {
        if (error) { clearTimeout(timer); this.pending.delete(id); reject(new HelperError('The PowerShell helper input closed: ' + error.message, 'helper-input')); }
      });
    });
  }

  close() {
    const child = this.child;
    if (!child) return;
    this.child = null;
    try { child.stdin.end(); child.kill(); } catch {}
    this.fail('The PowerShell helper was stopped.');
  }
}

module.exports = { HelperHost };
