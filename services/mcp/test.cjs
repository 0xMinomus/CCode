'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const runtime = require('../../src/main/mcp-catalog.cjs');
const catalog = require('./catalog.json');

async function main() {
  // A native server or installer must never flash a console window on Windows: both spawn
  // sites pass windowsHide, and the launcher is the only path that starts them.
  for (const file of [path.join(__dirname, 'launch.cjs'), path.join(__dirname, '../../src/main/mcp-catalog.cjs')]) {
    assert.match(fs.readFileSync(file, 'utf8'), /windowsHide: true/, path.basename(file) + ' must hide child consoles on Windows');
  }
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ccode-mcp-boundary-'));
  const resourcesPath = path.join(root, 'resources');
  const payload = path.join(resourcesPath, 'mcp');
  try {
    fs.mkdirSync(payload, { recursive: true });
    fs.copyFileSync(path.join(__dirname, 'catalog.json'), path.join(payload, 'catalog.json'));
    for (const item of catalog.filter(entry => entry.default)) {
      const executable = path.join(payload, 'runtime/node_modules', item.nativePackage || item.package, item.entry);
      fs.mkdirSync(path.dirname(executable), { recursive: true }); fs.writeFileSync(executable, 'boundary fixture');
    }
    const options = { root, resourcesPath, node: '/bundled/electron' };
    const config = runtime.paths(options).config;
    fs.mkdirSync(path.dirname(config), { recursive: true });
    fs.writeFileSync(config, JSON.stringify({ other: 'keep', mcp: { servers: { context7: { command: 'user-choice', disabled: true } } } }));
    runtime.bootstrap(options);
    const saved = JSON.parse(fs.readFileSync(config));
    assert.equal(saved.other, 'keep');
    assert.equal(saved.mcp.servers.context7.command, 'user-choice');
    assert.equal(saved.mcp.servers.context7.disabled, true);
    assert.equal(saved.mcp.servers.codegraph.command, '/bundled/electron');
    // Only the bundled payload seeds; the optional entries never appear on their own.
    assert.equal(Object.hasOwn(saved.mcp.servers, 'lsp'), false);
    assert.equal(Object.hasOwn(saved.mcp.servers, 'ripgrep'), false);
    delete saved.mcp.servers.codegraph; fs.writeFileSync(config, JSON.stringify(saved));
    runtime.bootstrap(options);
    assert.equal(Object.hasOwn(JSON.parse(fs.readFileSync(config)).mcp.servers, 'codegraph'), false, 'a deleted default is not reseeded');
    assert.equal(runtime.list(options).find(entry => entry.id === 'context7').status, 'disabled');
    // A user-owned server with a catalog name is never replaced or reinstalled.
    const concurrent = JSON.parse(fs.readFileSync(config));
    concurrent.mcp.servers.lsp = { command: 'user-choice' };
    fs.writeFileSync(config, JSON.stringify(concurrent));
    const refused = await runtime.install({ id: 'lsp' }, options);
    assert.equal(refused.ok, false);
    assert.match(refused.error, /already exists/);
    assert.equal(JSON.parse(fs.readFileSync(config)).mcp.servers.lsp.command, 'user-choice');
    assert.equal(runtime.trusted({ sender: { mainFrame: {} }, senderFrame: { url: 'https://evil/out/renderer/index.html' } }), false);
    const frame = { url: 'file:///resources/app.asar/out/renderer/index.html' };
    assert.equal(runtime.trusted({ sender: { mainFrame: frame }, senderFrame: frame }), true);
    const listed = JSON.stringify(runtime.list(options));
    assert.equal(listed.includes('user-choice'), false, 'user command is never echoed back to the renderer');
    assert.equal(listed.includes('installed'), true);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}

main().then(() => process.stdout.write('MCP catalog boundary checks passed\n'), error => { console.error(error); process.exitCode = 1; });
