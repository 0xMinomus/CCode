'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const runtime = require('../../src/main/mcp-catalog.cjs');
const catalog = require('./catalog.json');

async function relocationChecks() {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'ccode-mcp-relocation-'));
  const options = { root: path.join(temporary, 'namespace'), resourcesPath: path.join(temporary, 'current/resources'), node: process.execPath };
  const oldOptions = { root: path.join(temporary, 'deleted M1/namespace'), resourcesPath: path.join(temporary, 'deleted M1/resources'), node: path.join(temporary, 'deleted M1/CCode.exe') };
  const p = runtime.paths(options), old = runtime.paths(oldOptions), installs = path.join(temporary, 'installs.log');
  const config = () => JSON.parse(fs.readFileSync(p.config, 'utf8'));
  const save = servers => fs.writeFileSync(p.config, JSON.stringify({ other: 'keep', mcp: { settings: { keep: true }, servers } }));
  const executable = item => path.join(item.default ? path.join(p.payload, 'runtime') : path.join(p.state, 'packages', item.id), 'node_modules', item.nativePackage || item.package, item.entry);
  const stale = item => {
    const server = runtime.definition(old, item);
    server.args.push('--user-flag');
    Object.assign(server, { disabled: true, enabled: false, timeout: 12345, settings: { keep: true } });
    server.env.KEEP = 'user-value';
    const override = Object.keys(item.env || {})[0];
    if (override) server.env[override] = 'user-override';
    return server;
  };
  const expected = (item, server) => {
    const current = runtime.definition(p, item);
    return { ...server, command: current.command, args: [...current.args, ...server.args.slice(4)], env: { ...current.env, ...server.env } };
  };
  try {
    fs.mkdirSync(p.payload, { recursive: true });
    fs.copyFileSync(path.join(__dirname, 'catalog.json'), path.join(p.payload, 'catalog.json'));
    fs.mkdirSync(path.dirname(p.config), { recursive: true });
    fs.mkdirSync(p.state, { recursive: true });
    fs.writeFileSync(path.join(p.state, 'default-seed.json'), JSON.stringify({ seeded: catalog.filter(item => item.default).map(item => item.id) }));
    for (const item of catalog) {
      const entry = executable(item);
      fs.mkdirSync(path.dirname(entry), { recursive: true });
      fs.writeFileSync(entry, 'healthy payload');
    }
    const npm = path.join(p.payload, 'runtime/node_modules/npm/bin/npm-cli.js');
    fs.mkdirSync(path.dirname(npm), { recursive: true });
    fs.writeFileSync(npm, [
      "const fs = require('node:fs'), path = require('node:path');",
      'const entries = ' + JSON.stringify(Object.fromEntries(catalog.filter(item => !item.default).map(item => [item.id, executable(item)]))) + ';',
      'const id = path.basename(process.cwd()), entry = entries[id];',
      'if (!entry) throw Error("Unexpected package installation");',
      'fs.appendFileSync(' + JSON.stringify(installs) + ', id + "\\n");',
      'fs.mkdirSync(path.dirname(entry), { recursive: true }); fs.writeFileSync(entry, "repaired payload");',
    ].join('\n'));

    const servers = Object.fromEntries(catalog.map(item => [item.id, stale(item)]));
    save(servers);
    runtime.bootstrap(options);
    for (const item of catalog) assert.deepEqual(config().mcp.servers[item.id], expected(item, servers[item.id]), item.id + ' relocates after seeding, including optional installs');
    assert.equal(config().other, 'keep');
    assert.deepEqual(config().mcp.settings, { keep: true });
    const healed = fs.readFileSync(p.config, 'utf8');
    runtime.bootstrap(options);
    assert.equal(fs.readFileSync(p.config, 'utf8'), healed, 'healing is idempotent');
    const deleted = config().mcp.servers;
    delete deleted.codegraph; delete deleted.lsp;
    save(deleted);
    runtime.bootstrap(options);
    assert.equal(Object.hasOwn(config().mcp.servers, 'codegraph'), false, 'deleted defaults stay deleted after relocation');
    assert.equal(Object.hasOwn(config().mcp.servers, 'lsp'), false, 'optional installs stay deleted');

    // A seed marker or catalog id alone never proves ownership of a user's definition.
    for (const item of catalog) {
      for (const change of [
        server => { server.command = 'user-choice'; },
        server => { server.args[0] = path.join(temporary, 'user/launch.cjs'); },
        server => { server.args[1] = 'another-id'; },
        server => { server.args[2] = path.join(temporary, 'user/runtime'); },
        server => { server.args[3] = path.join(temporary, 'user/home'); },
        server => { server.env = { KEEP: 'user-value' }; },
      ]) {
        const server = stale(item);
        change(server);
        save({ [item.id]: server });
        runtime.bootstrap(options);
        assert.deepEqual(config().mcp.servers[item.id], server, item.id + ' user-owned definition survives bootstrap');
        const result = await runtime.install({ id: item.id }, options);
        assert.equal(result.ok, false);
        assert.match(result.error, /already exists/);
        assert.deepEqual(config().mcp.servers[item.id], server, item.id + ' user-owned definition survives install');
      }
    }
    assert.equal(fs.existsSync(installs), false, 'bootstrap and refused installs never download packages');

    save(servers);
    for (const item of catalog) {
      assert.deepEqual(await runtime.install({ id: item.id }, options), { ok: true }, item.id + ' stale-tree definition can be repaired explicitly');
      assert.deepEqual(config().mcp.servers[item.id], expected(item, servers[item.id]));
      assert.deepEqual(await runtime.install({ id: item.id }, options), { ok: true }, item.id + ' healthy managed install is idempotent');
    }
    assert.equal(fs.existsSync(installs), false, 'healthy optional payloads are reused, not reinstalled');

    const optional = catalog.find(item => !item.default);
    fs.unlinkSync(executable(optional));
    const missing = config().mcp.servers;
    missing[optional.id] = stale(optional);
    save(missing);
    runtime.bootstrap(options);
    assert.deepEqual(config().mcp.servers[optional.id], expected(optional, missing[optional.id]), 'missing optional payload still gets current launch paths');
    assert.equal(runtime.list(options).find(item => item.id === optional.id).status, 'not-installed');
    assert.equal(fs.existsSync(installs), false, 'bootstrap never reinstalls missing optional payloads');
    missing[optional.id] = stale(optional);
    save(missing);
    assert.deepEqual(await runtime.install({ id: optional.id }, options), { ok: true }, 'explicit repair installs a missing optional payload');
    assert.deepEqual(config().mcp.servers[optional.id], expected(optional, missing[optional.id]));
    assert.equal(fs.readFileSync(installs, 'utf8'), optional.id + '\n', 'only the missing optional payload was installed');
  } finally { fs.rmSync(temporary, { recursive: true, force: true }); }
}

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
  await relocationChecks();
}

main().then(() => process.stdout.write('MCP catalog boundary checks passed\n'), error => { console.error(error); process.exitCode = 1; });
