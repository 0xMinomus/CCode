'use strict';
const fs = require('node:fs'), path = require('node:path'), { spawnSync } = require('node:child_process');
const dest = process.argv[2];
if (!dest || !path.isAbsolute(dest)) throw Error('Usage: node services/mcp/stage.cjs <absolute resources/mcp directory>');
const runtime = path.join(dest, 'runtime');
fs.mkdirSync(runtime, { recursive: true });
for (const file of ['package.json', 'package-lock.json']) fs.copyFileSync(path.join(__dirname, file), path.join(runtime, file));
// npm resolves through cmd.exe on Windows; run its CLI with this Node instead of a shell.
const npmArgs = ['ci', '--omit=dev', '--ignore-scripts', '--no-audit', '--no-fund'];
const npmCli = path.join(path.dirname(process.execPath), 'node_modules/npm/bin/npm-cli.js');
const installed = process.platform === 'win32' && fs.existsSync(npmCli)
  ? spawnSync(process.execPath, [npmCli, ...npmArgs], { cwd: runtime, stdio: 'inherit', timeout: 300000 })
  : spawnSync('npm', npmArgs, { cwd: runtime, stdio: 'inherit', timeout: 300000 });
if (installed.error || installed.status !== 0) throw Error('Pinned MCP dependency staging failed.');
const catalog = require('./catalog.json');
// Native engines are optional packages pinned per platform in the lockfile; npm ci installs
// the variant matching this host, so the staged catalog must name that same variant.
const hostVariant = name => name.replace(/-(linux|win32|darwin|freebsd)-(x64|arm64|ia32|armv7l)$/,
  '-' + process.platform + '-' + process.arch);
const resolved = catalog.map(entry => {
  const next = { ...entry };
  if (entry.nativePackage) next.nativePackage = hostVariant(entry.nativePackage);
  if (entry.dependencies) next.dependencies = Object.fromEntries(
    Object.entries(entry.dependencies).map(([name, version]) => [hostVariant(name), version]));
  if (next.nativePackage && process.platform === 'win32' && !next.entry.endsWith('.exe')) next.entry += '.exe';
  return next;
});
for (const entry of resolved.filter(item => item.default)) {
  const pkg = path.join(runtime, 'node_modules', entry.nativePackage || entry.package);
  if (!fs.existsSync(path.join(pkg, entry.entry))) throw Error('Missing packaged executable: ' + entry.id);
  if (entry.nativePackage) fs.chmodSync(path.join(pkg, entry.entry), 0o755);
}
// Only the native engine is launched; Claude plugin prompts, hooks and installers are not integrated.
fs.rmSync(path.join(runtime, 'node_modules/@sdsrs/code-graph/claude-plugin'), { recursive: true, force: true });
fs.writeFileSync(path.join(dest, 'catalog.json'), JSON.stringify(resolved, null, 2) + '\n');
for (const file of ['launch.cjs', 'smoke.cjs']) fs.copyFileSync(path.join(__dirname, file), path.join(dest, file));
fs.copyFileSync(path.join(__dirname, '../../src/main/mcp-catalog.cjs'), path.join(dest, 'main.cjs'));
// Retire payload left by builds that bundled the now-downloadable plugin.
fs.rmSync(path.join(dest, 'plugins/n8n'), { recursive: true, force: true });
