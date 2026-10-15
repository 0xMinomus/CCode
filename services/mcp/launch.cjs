'use strict';
const fs = require('node:fs'), path = require('node:path'), { spawn } = require('node:child_process');
const catalog = require('./catalog.json');
const [id, runtime, home, ...extra] = process.argv.slice(2);
const item = catalog.find(entry => entry.id === id);
if (!item?.package || !path.isAbsolute(runtime || '') || !path.isAbsolute(home || '')) throw Error('Invalid MCP launch');
const env = {};
for (const key of ['PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT', 'TEMP', 'TMP', 'USERPROFILE',
  'APPDATA', 'LOCALAPPDATA', 'PROGRAMDATA', 'COMSPEC', 'PATHEXT', 'NUMBER_OF_PROCESSORS', 'OS',
  'PROCESSOR_ARCHITECTURE']) if (process.env[key]) env[key] = process.env[key];
Object.assign(env, item.env, { HOME: home, XDG_CONFIG_HOME: path.join(home, '.config'), XDG_CACHE_HOME: path.join(home, '.cache'), ELECTRON_RUN_AS_NODE: '1' });
// Node and the language-server bridge resolve the home directory from USERPROFILE on Windows,
// so the state home must replace it there too or per-user config lands outside the namespace.
if (process.platform === 'win32') env.USERPROFILE = home;
fs.mkdirSync(home, { recursive: true, mode: 0o700 });
const bin = path.join(home, 'bin');
fs.mkdirSync(bin, { recursive: true, mode: 0o700 });
const win = process.platform === 'win32';
const quote = text => "'" + text.replaceAll("'", "'\\''") + "'";
if (!win) {
  fs.writeFileSync(path.join(bin, 'node'), '#!/bin/sh\nELECTRON_RUN_AS_NODE=1 exec ' + quote(process.execPath) + ' "$@"\n', { mode: 0o700 });
} else {
  fs.writeFileSync(path.join(bin, 'node.cmd'), '@echo off\r\nset "ELECTRON_RUN_AS_NODE=1"\r\n"' + process.execPath + '" %*\r\n');
}
if (id === 'lsp') {
  const cli = path.join(runtime, 'node_modules/typescript-language-server/lib/cli.mjs');
  if (!win) fs.writeFileSync(path.join(bin, 'typescript-language-server'), '#!/bin/sh\nexec ' + quote(path.join(bin, 'node')) + ' ' + quote(cli) + ' "$@"\n', { mode: 0o700 });
  else {
    fs.writeFileSync(path.join(bin, 'typescript-language-server.cmd'), '@echo off\r\nset "ELECTRON_RUN_AS_NODE=1"\r\n"' + process.execPath + '" "' + cli + '" %*\r\n');
    // The pinned bridge spawns `typescript-language-server` by bare name, which Windows
    // cannot resolve to a .cmd; point its built-in TypeScript server at this runtime
    // instead (config is read from the state home).
    fs.writeFileSync(path.join(home, '.lsp-mcp.json'), JSON.stringify({
      servers: [{
        id: 'typescript',
        extensions: ['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'],
        languageIds: ['typescript', 'typescriptreact', 'javascript', 'javascriptreact'],
        command: process.execPath,
        args: [cli, '--stdio'],
        rootPatterns: ['tsconfig.json', 'jsconfig.json', 'package.json'],
      }],
    }, null, 2) + '\n');
  }
}
if (id === 'ripgrep') {
  const dep = Object.keys(item.dependencies || {}).find(name => name.startsWith('@vscode/ripgrep'));
  const rg = path.join(runtime, 'node_modules', dep || '@vscode/ripgrep-linux-x64', 'bin', win ? 'rg.exe' : 'rg');
  if (!fs.existsSync(rg)) throw Error('Bundled ripgrep binary is missing');
  const link = path.join(bin, win ? 'rg.cmd' : 'rg');
  try { fs.unlinkSync(link); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (!win) fs.symlinkSync(rg, link);
  else {
    // mcp-ripgrep builds a POSIX-quoted command (`'arg'`, `'"'"'` escapes) and spawns it
    // through cmd.exe, which treats single quotes literally; undo that quoting first.
    const shim = [
      "'use strict';",
      'const { spawnSync } = require("node:child_process");',
      'const sentinel = "\\u0000";',
      'const raw = process.argv.slice(2).join(" ").split("\\u0027\\u0022\\u0027\\u0022\\u0027").join(sentinel);',
      'const args = []; let current = "", quoted = false, any = false;',
      'for (const ch of raw) {',
      '  if (ch === "\'") { quoted = !quoted; any = true; continue; }',
      '  if (ch === " " && !quoted) { if (any || current) { args.push(current.split(sentinel).join("\'")); current = ""; any = false; } continue; }',
      '  current += ch;',
      '}',
      'if (any || current) args.push(current.split(sentinel).join("\'"));',
      'const result = spawnSync(' + JSON.stringify(rg) + ', args, { stdio: "inherit" });',
      'process.exit(result.status === null ? 1 : result.status);',
      '',
    ].join('\r\n');
    fs.writeFileSync(path.join(bin, 'rg-shim.cjs'), shim);
    fs.writeFileSync(link, '@echo off\r\n"' + process.execPath + '" "%~dp0rg-shim.cjs" %*\r\n');
  }
}
env.PATH = bin + path.delimiter + (env.PATH || (win ? 'C:\\Windows\\system32;C:\\Windows' : '/usr/bin:/bin'));
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
