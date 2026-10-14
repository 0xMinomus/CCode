'use strict';
const fs = require('node:fs'), path = require('node:path'), { spawn } = require('node:child_process');
const catalog = require('./catalog.json');
const [id, runtime, home, ...extra] = process.argv.slice(2);
const item = catalog.find(entry => entry.id === id);
if (!item?.package || !path.isAbsolute(runtime || '') || !path.isAbsolute(home || '')) throw Error('Invalid MCP launch');
const env = {};
for (const key of ['PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT']) if (process.env[key]) env[key] = process.env[key];
Object.assign(env, item.env, { HOME: home, XDG_CONFIG_HOME: path.join(home, '.config'), XDG_CACHE_HOME: path.join(home, '.cache'), ELECTRON_RUN_AS_NODE: '1' });
fs.mkdirSync(home, { recursive: true, mode: 0o700 });
const bin = path.join(home, 'bin');
fs.mkdirSync(bin, { recursive: true, mode: 0o700 });
const quote = text => "'" + text.replaceAll("'", "'\\''") + "'";
fs.writeFileSync(path.join(bin, 'node'), '#!/bin/sh\nELECTRON_RUN_AS_NODE=1 exec ' + quote(process.execPath) + ' "$@"\n', { mode: 0o700 });
if (id === 'lsp') fs.writeFileSync(path.join(bin, 'typescript-language-server'), '#!/bin/sh\nexec ' + quote(path.join(bin, 'node')) + ' ' + quote(path.join(runtime, 'node_modules/typescript-language-server/lib/cli.mjs')) + ' "$@"\n', { mode: 0o700 });
if (id === 'ripgrep') {
  const rg = path.join(runtime, 'node_modules/@vscode/ripgrep-linux-x64/bin/rg');
  if (!fs.existsSync(rg)) throw Error('Bundled ripgrep binary is missing');
  const link = path.join(bin, 'rg');
  try { fs.unlinkSync(link); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  fs.symlinkSync(rg, link);
}
env.PATH = bin + path.delimiter + (env.PATH || '/usr/bin:/bin');
const entry = path.join(runtime, 'node_modules', item.nativePackage || item.package, item.entry);
const command = item.nativePackage ? entry : process.execPath;
const args = item.nativePackage ? extra : [entry, ...extra];
const child = spawn(command, args, { cwd: ['codegraph', 'lsp'].includes(id) ? process.cwd() : home, env, stdio: 'inherit', detached: process.platform !== 'win32' });
let stopping = false;
function stop(signal) {
  if (stopping) return;
  stopping = true;
  try { process.kill(process.platform === 'win32' ? child.pid : -child.pid, signal); } catch {}
  setTimeout(() => { try { process.kill(process.platform === 'win32' ? child.pid : -child.pid, 'SIGKILL'); } catch {} process.exit(1); }, 1500).unref();
}
process.on('SIGTERM', () => stop('SIGTERM'));
process.on('SIGINT', () => stop('SIGINT'));
child.on('error', () => { process.stderr.write('MCP executable could not start.\n'); process.exit(1); });
child.on('exit', code => { try { process.kill(-child.pid, 'SIGKILL'); } catch {} process.exit(code ?? 1); });
