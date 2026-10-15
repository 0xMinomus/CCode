'use strict';
const fs = require('node:fs'), path = require('node:path'), { spawnSync } = require('node:child_process');
const dest = process.argv[2];
if (!dest || !path.isAbsolute(dest)) throw Error('Usage: node services/mcp/stage.cjs <absolute resources/mcp directory>');
const runtime = path.join(dest, 'runtime');
fs.mkdirSync(runtime, { recursive: true });
for (const file of ['package.json', 'package-lock.json']) fs.copyFileSync(path.join(__dirname, file), path.join(runtime, file));
const installed = spawnSync('npm', ['ci', '--omit=dev', '--ignore-scripts', '--no-audit', '--no-fund'], { cwd: runtime, stdio: 'inherit', timeout: 300000 });
if (installed.error || installed.status !== 0) throw Error('Pinned MCP dependency staging failed.');
const catalog = require('./catalog.json');
for (const entry of catalog.filter(item => item.default)) {
  const pkg = path.join(runtime, 'node_modules', entry.nativePackage || entry.package);
  if (!fs.existsSync(path.join(pkg, entry.entry))) throw Error('Missing packaged executable: ' + entry.id);
  if (entry.nativePackage) fs.chmodSync(path.join(pkg, entry.entry), 0o755);
}
// Only the native engine is launched; Claude plugin prompts, hooks and installers are not integrated.
fs.rmSync(path.join(runtime, 'node_modules/@sdsrs/code-graph/claude-plugin'), { recursive: true, force: true });
for (const file of ['catalog.json', 'launch.cjs', 'smoke.cjs']) fs.copyFileSync(path.join(__dirname, file), path.join(dest, file));
fs.copyFileSync(path.join(__dirname, '../../src/main/mcp-catalog.cjs'), path.join(dest, 'main.cjs'));
// Retire payload left by builds that bundled the now-downloadable plugin.
fs.rmSync(path.join(dest, 'plugins/n8n'), { recursive: true, force: true });
