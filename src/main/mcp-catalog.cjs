'use strict';
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const { spawn } = require('node:child_process');
const { pathToFileURL, fileURLToPath } = require('node:url');
const active = new Set(), busy = new Set();
// Computer Use registers itself as `linux-desktop` on Linux and `windows-desktop` on Windows:
// one backend per platform, and neither id is ever seeded on the other. The legacy name is only
// read on Linux, where it predates the rename.
const DESKTOP_SERVER = process.platform === 'win32' ? 'windows-desktop' : 'linux-desktop',
  DESKTOP_SERVER_LEGACY = 'fedora-desktop';
// The standalone root mirrors src/local_only/storage.py: %LOCALAPPDATA%\CCode on Windows with a
// homedir fallback, ~/.local/share/ccode elsewhere.
function standaloneRoot() {
  if (process.platform !== 'win32') return path.join(os.homedir(), '.local/share/ccode');
  return path.join((process.env.LOCALAPPDATA || '').trim() || path.join(os.homedir(), 'AppData', 'Local'), 'CCode');
}
function paths(options = {}) {
  const resources = path.resolve(options.resourcesPath || process.resourcesPath || path.join(__dirname, '../../app/resources'));
  const root = path.resolve(options.root || process.env.CCODE_STANDALONE_ROOT || standaloneRoot());
  return { resources, root, payload: path.join(resources, 'mcp'), state: path.join(root, 'mcp'), config: path.join(root, 'data/.ccode/cli/config.json'), node: options.node || process.execPath };
}
function catalog(p) { return JSON.parse(fs.readFileSync(path.join(p.payload, 'catalog.json'), 'utf8')); }
function object(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function readConfig(p) {
  let raw = null, data = {};
  try { raw = fs.readFileSync(p.config, 'utf8'); data = JSON.parse(raw); } catch (error) { if (error.code !== 'ENOENT') throw Error('Cannot read the standalone MCP configuration.'); }
  if (!object(data) || (data.mcp !== undefined && !object(data.mcp)) || (data.mcp?.servers !== undefined && !object(data.mcp.servers))) throw Error('Invalid standalone MCP configuration.');
  data.mcp ??= {}; data.mcp.servers ??= {};
  return { raw, data };
}
function atomic(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const temp = file + '.' + process.pid + '.' + require('node:crypto').randomUUID();
  try { fs.writeFileSync(temp, JSON.stringify(value, null, 2) + '\n', { mode: 0o600, flag: 'wx' }); fs.renameSync(temp, file); }
  finally { try { fs.unlinkSync(temp); } catch {} }
}
function commit(p, snapshot) {
  let current = null;
  try { current = fs.readFileSync(p.config, 'utf8'); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (current !== snapshot.raw) throw Error('MCP settings changed concurrently. Retry the operation.');
  atomic(p.config, snapshot.data);
}
function runtimePath(p, item) { return item.default ? path.join(p.payload, 'runtime') : path.join(p.state, 'packages', item.id); }
function executable(p, item) { return path.join(runtimePath(p, item), 'node_modules', item.nativePackage || item.package, item.entry); }
function definition(p, item) {
  const env = { ELECTRON_RUN_AS_NODE: '1', ...item.env };
  return { command: p.node, args: [path.join(p.payload, 'launch.cjs'), item.id, runtimePath(p, item), path.join(p.state, 'home', item.id)], env };
}
// The seed marker records deletions, not ownership. Only the catalog launcher's full path
// layout and Electron environment identify an entry that is safe to relocate.
function managedDefinition(server, item) {
  if (!object(server) || typeof server.command !== 'string' || !path.isAbsolute(server.command) ||
      !Array.isArray(server.args) || !object(server.env) || server.env.ELECTRON_RUN_AS_NODE !== '1') return false;
  const [launch, id, runtime, home] = server.args;
  if (id !== item.id || ![launch, runtime, home].every(value => typeof value === 'string' && path.isAbsolute(value))) return false;
  const payload = path.dirname(launch), state = path.dirname(path.dirname(home));
  return path.basename(payload) === 'mcp' && path.basename(state) === 'mcp' &&
    path.normalize(launch) === path.join(payload, 'launch.cjs') &&
    path.normalize(home) === path.join(state, 'home', item.id) &&
    path.normalize(runtime) === (item.default ? path.join(payload, 'runtime') : path.join(state, 'packages', item.id));
}
function applyManagedDefinition(p, item, server) {
  const value = definition(p, item);
  let changed = false;
  if (server.command !== value.command) { server.command = value.command; changed = true; }
  for (const [index, arg] of value.args.entries()) if (server.args[index] !== arg) { server.args[index] = arg; changed = true; }
  for (const [name, setting] of Object.entries(value.env)) if (!Object.hasOwn(server.env, name)) { server.env[name] = setting; changed = true; }
  return changed;
}
function projectRoot(resources) {
  for (let dir = path.resolve(resources);; dir = path.dirname(dir)) {
    if (fs.existsSync(path.join(dir, 'project.json'))) return dir;
    if (path.dirname(dir) === dir) return null;
  }
}
// The desktop backend lives beside the application, so its absolute paths depend on where
// the tree sits: a package prefix, a source checkout, or a fresh AppImage mount each run.
function desktopDefinition(p) {
  if (process.platform === 'win32') return windowsDesktopDefinition(p);
  if (process.platform !== 'linux') return null;
  const root = projectRoot(p.resources);
  if (!root) return null;
  const command = path.join(root, 'services/desktop/bin/screen-mcp');
  if (!fs.existsSync(command)) return null;
  return { command, args: [], env: { SCREEN_PYTHON: path.join(root, 'services/desktop/.venv/bin/python'),
    MCP_SCREEN_NO_AUTO_DEPS: '1', MCP_SCREEN_PROFILE: 'ccode-fast', MCP_SCREEN_MAX_EDGE: '1280',
    MCP_SCREEN_MAX_OUTPUT_KB: '250', MCP_SCREEN_ATSPI: '1' } };
}
// The Windows backend is a Node stdio server run by Electron-as-Node (no Python runtime in the
// package). Packaged trees ship it under resources/desktop-win; checkouts keep it in services.
function windowsDesktopDefinition(p) {
  const root = projectRoot(p.resources);
  const script = [path.join(p.resources, 'desktop-win/main.cjs'), root && path.join(root, 'services/desktop-win/main.cjs')]
    .find(candidate => candidate && fs.existsSync(candidate));
  if (!script) return null;
  return { command: p.node, args: [script], env: { ELECTRON_RUN_AS_NODE: '1', MCP_SCREEN_PROFILE: 'ccode-fast',
    MCP_SCREEN_MAX_EDGE: '1280', MCP_SCREEN_MAX_OUTPUT_KB: '250' } };
}
function applyDesktopDefinition(server, value) {
  server.command = value.command;
  // The Windows backend's single argument names the launcher script inside the tree, so a moved
  // install folder would otherwise leave it stale. Refresh it only while it still points at that
  // script; a user who replaced the backend keeps their own args.
  const managed = Array.isArray(server.args) && value.args.length === 1 && server.args.length === 1
    && /[\\/]desktop-win[\\/]main\.cjs$/.test(String(server.args[0]));
  if (!Array.isArray(server.args) || managed) server.args = value.args;
  const env = object(server.env) ? server.env : (server.env = {});
  for (const [name, setting] of Object.entries(value.env)) if (!(name in env)) env[name] = setting;
}
// Seeds the Computer Use server for any layout that ships its backend. The marker keeps a
// deliberate deletion deleted, while an existing entry is refreshed because an AppImage mount
// point (or a moved Windows install folder) changes between runs.
function seedDesktopServer(p, snapshot, seeded) {
  const platform = process.platform;
  if (platform !== 'linux' && platform !== 'win32') return false;
  const servers = snapshot.data.mcp.servers, value = desktopDefinition(p);
  const seededBefore = seeded.includes(DESKTOP_SERVER);
  const legacy = servers[DESKTOP_SERVER_LEGACY];
  if (platform === 'linux' && !Object.hasOwn(servers, DESKTOP_SERVER) && object(legacy)) {
    servers[DESKTOP_SERVER] = legacy;
    delete servers[DESKTOP_SERVER_LEGACY];
    if (value) applyDesktopDefinition(servers[DESKTOP_SERVER], value);
    if (!seededBefore) seeded.push(DESKTOP_SERVER);
    return true;
  }
  if (Object.hasOwn(servers, DESKTOP_SERVER)) {
    if (!seededBefore) seeded.push(DESKTOP_SERVER);
    if (!value || !object(servers[DESKTOP_SERVER])) return !seededBefore;
    const before = JSON.stringify(servers[DESKTOP_SERVER]);
    applyDesktopDefinition(servers[DESKTOP_SERVER], value);
    return JSON.stringify(servers[DESKTOP_SERVER]) !== before;
  }
  if (seededBefore || !value) return false;
  servers[DESKTOP_SERVER] = value;
  seeded.push(DESKTOP_SERVER);
  return true;
}
function bootstrap(options = {}) {
  const p = paths(options), entries = catalog(p), marker = path.join(p.state, 'default-seed.json');
  let seeded = [];
  try { seeded = JSON.parse(fs.readFileSync(marker, 'utf8')).seeded; if (!Array.isArray(seeded)) throw Error(); }
  catch (error) { if (error.code !== 'ENOENT') throw Error('Invalid MCP default seed marker.'); }
  const snapshot = readConfig(p);
  let changed = false;
  for (const item of entries) {
    const server = snapshot.data.mcp.servers[item.id];
    if (managedDefinition(server, item) && applyManagedDefinition(p, item, server)) changed = true;
    if (!item.default || seeded.includes(item.id)) continue;
    if (!fs.existsSync(executable(p, item))) throw Error('Bundled MCP payload is incomplete: ' + item.name);
    if (!Object.hasOwn(snapshot.data.mcp.servers, item.id)) { snapshot.data.mcp.servers[item.id] = definition(p, item); changed = true; }
    seeded.push(item.id);
  }
  if (seedDesktopServer(p, snapshot, seeded)) changed = true;
  if (changed) commit(p, snapshot);
  atomic(marker, { seeded });
  return { ok: true };
}
function itemFor(p, id) {
  if (typeof id !== 'string') throw Error('Unknown MCP catalog entry.');
  const item = catalog(p).find(entry => entry.id === id);
  if (!item) throw Error('Unknown MCP catalog entry.');
  return item;
}
function list(options = {}) {
  const p = paths(options), servers = readConfig(p).data.mcp.servers;
  return catalog(p).map(item => {
    const configured = Object.hasOwn(servers, item.id), present = !item.package || fs.existsSync(executable(p, item));
    const installed = configured && present;
    const server = servers[item.id];
    return { id: item.id, name: item.name, description: item.description, default: item.default, installed,
      status: busy.has(item.id) ? 'installing' : !installed ? 'not-installed' : server?.disabled || server?.enabled === false ? 'disabled' : 'installed',
      error: !present && configured ? 'Installed package is missing. Install again.' : null };
  });
}
function cleanEnv(home) {
  const env = {};
  for (const key of ['PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT', 'TEMP', 'TMP', 'USERPROFILE',
    'APPDATA', 'LOCALAPPDATA', 'PROGRAMDATA', 'COMSPEC', 'PATHEXT', 'NUMBER_OF_PROCESSORS', 'OS',
    'PROCESSOR_ARCHITECTURE']) if (process.env[key]) env[key] = process.env[key];
  return { ...env, HOME: home, XDG_CONFIG_HOME: path.join(home, '.config'), XDG_CACHE_HOME: path.join(home, '.cache'), ELECTRON_RUN_AS_NODE: '1' };
}
function npmInstall(p, item) {
  const dir = runtimePath(p, item), home = path.join(p.state, 'installer-home');
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 }); fs.mkdirSync(home, { recursive: true, mode: 0o700 });
  atomic(path.join(dir, 'package.json'), { name: 'ccode-mcp-' + item.id, version: '1.0.0', private: true, dependencies: { [item.package]: item.version, ...item.dependencies } });
  const npm = path.join(p.payload, 'runtime/node_modules/npm/bin/npm-cli.js');
  return new Promise((resolve, reject) => {
    const child = spawn(p.node, [npm, 'install', '--omit=dev', '--ignore-scripts', '--no-audit', '--no-fund', '--userconfig=' + path.join(home, '.npmrc'), '--cache=' + path.join(p.state, 'npm-cache')], { cwd: dir, env: cleanEnv(home), stdio: 'ignore', windowsHide: true, detached: process.platform !== 'win32' });
    const cancel = () => { try { process.kill(process.platform === 'win32' ? child.pid : -child.pid, 'SIGKILL'); } catch {} };
    active.add(cancel);
    const timer = setTimeout(cancel, 180000);
    child.once('error', () => { clearTimeout(timer); active.delete(cancel); reject(Error('The private npm installer could not start.')); });
    child.once('close', code => { clearTimeout(timer); active.delete(cancel); code === 0 ? resolve() : reject(Error('Package installation failed or timed out. Check network access and retry.')); });
  });
}
async function install(request, options = {}) {
  const p = paths(options), item = itemFor(p, request?.id);
  if (busy.has(item.id)) return { ok: false, error: 'An operation for this server is already running.' };
  busy.add(item.id);
  try {
    const configured = readConfig(p).data.mcp.servers, existing = configured[item.id];
    const repair = managedDefinition(existing, item);
    if (Object.hasOwn(configured, item.id) && !repair) throw Error('A server with this name already exists. Edit or remove it in the native MCP server list before reinstalling.');
    if (item.package && !item.default && !fs.existsSync(executable(p, item))) await npmInstall(p, item);
    if (item.package && !fs.existsSync(executable(p, item))) throw Error('The bundled server executable is missing.');
    const snapshot = readConfig(p), servers = snapshot.data.mcp.servers;
    if (repair) {
      if (JSON.stringify(servers[item.id]) !== JSON.stringify(existing)) throw Error('MCP settings changed concurrently. Retry the operation.');
      if (applyManagedDefinition(p, item, servers[item.id])) commit(p, snapshot);
    } else {
      if (Object.hasOwn(servers, item.id)) throw Error('MCP settings changed concurrently. Retry the operation.');
      servers[item.id] = definition(p, item);
      commit(p, snapshot);
    }
    return { ok: true };
  } catch (error) { return { ok: false, error: error.code ? 'MCP configuration could not be saved. Check file permissions and retry.' : error.message }; }
  finally { busy.delete(item.id); }
}
async function sdk(p) {
  const base = path.join(p.payload, 'runtime/node_modules/@modelcontextprotocol/sdk/dist/esm/client');
  const [{ Client }, { StdioClientTransport }] = await Promise.all(['index.js', 'stdio.js'].map(file => import(pathToFileURL(path.join(base, file)).href)));
  return { Client, StdioClientTransport };
}
function textResult(result) { return (result.content || []).filter(part => part.type === 'text').map(part => part.text).join('\n'); }
function jsonResult(result) {
  if (object(result.structuredContent)) return result.structuredContent;
  try { return JSON.parse(textResult(result)); } catch { return null; }
}
function checkResult(result) {
  const text = textResult(result);
  const data = jsonResult(result);
  if (result.isError || data?.error || data?.success === false || /^\s*(Error:|Failed|Unauthorized|Authentication failed)/i.test(text)) {
    throw Error('The server returned a tool error. Check its connectivity and prerequisites.');
  }
  if (!text.trim() && !result.structuredContent) throw Error('The server returned no tool output.');
  return text;
}
async function probe(client, item, dir, timeout) {
  const call = async (name, args) => {
    try {
      const result = await client.callTool({ name, arguments: args }, undefined, { timeout });
      checkResult(result);
      return result;
    } catch (error) {
      error.mcpTool = name;
      throw error;
    }
  };
  if (item.id === 'context7') {
    const resolved = await call('resolve-library-id', { libraryName: 'React', query: 'React useState hook' });
    const libraryId = /Context7-compatible library ID:\s*(\/[^\s]+)/i.exec(textResult(resolved))?.[1];
    if (!libraryId) throw Error('Context7 did not resolve a library.');
    const docs = await call('query-docs', { libraryId, query: 'useState hook example' });
    if (!/useState/i.test(textResult(docs))) throw Error('Context7 did not return the requested documentation.');
    return 'Resolved React and read useState documentation';
  }
  if (item.id === 'codegraph') {
    const found = await call('get_ast_node', { symbol_name: 'ccodeSmokeAdd' });
    if (!textResult(found).includes('ccodeSmokeAdd')) throw Error('Codegraph did not find the indexed fixture symbol.');
    return 'Indexed local code and retrieved its AST symbol';
  }
  if (item.id === 'lsp') {
    const file = path.join(dir, 'smoke.ts');
    // A cold server can refuse or truncate the first symbol read while the project loads, so the
    // open+read pair is retried. The assertion itself is unchanged.
    let found = null, symbolError = null;
    for (let attempt = 0; attempt < 3 && !found; attempt++) {
      if (attempt > 0) await new Promise(resolve => setTimeout(resolve, 2000));
      try {
        await call('lsp_index_files', { files: [file] });
        const read = await call('lsp_document_symbols', { file_path: file });
        if (textResult(read).includes('ccodeSmokeAdd')) found = read;
      } catch (error) { symbolError = error; }
    }
    if (!found) {
      const failure = Error('Language server did not return the fixture symbol.' + (symbolError ? ' ' + symbolError.message : ''));
      failure.mcpTool = 'lsp_document_symbols';
      throw failure;
    }
    if (process.platform !== 'win32') {
      const diagnostics = await call('lsp_diagnostics', { file_path: file, severity_filter: 'all' });
      if (!/2322|not assignable/i.test(textResult(diagnostics))) throw Error('Language server did not report the fixture type error.');
      return 'lsp_document_symbols found the function; lsp_diagnostics reported its known TypeScript type error';
    }
    // lsp_workspace_diagnostics is cache-only: it reports nothing until the file has been opened
    // in the session, so each pass refreshes with lsp_diagnostics first. That per-file answer is
    // empty on Windows (the server publishes lowercase-drive URIs while it keys on the caller's
    // spelling), which is why the workspace view is what the assertion reads.
    const deadline = Date.now() + 10000;
    for (;;) {
      try { await call('lsp_diagnostics', { file_path: file, severity_filter: 'all' }); }
      catch { /* the refresh only has to open the file; its own answer is not asserted here */ }
      const diagnostics = await call('lsp_workspace_diagnostics', { severity_filter: 'all', limit: 200 });
      if (/2322|not assignable/i.test(textResult(diagnostics))) {
        return 'lsp_document_symbols found the function; lsp_workspace_diagnostics reported its known TypeScript type error (per-file lsp_diagnostics is empty on Windows)';
      }
      if (Date.now() >= deadline) throw Error('Language server did not report the fixture type error.');
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
  if (item.id === 'ripgrep') {
    const found = await call('search', { pattern: 'ccodeSmokeAdd', path: dir });
    if (!textResult(found).includes('ccodeSmokeAdd')) throw Error('Ripgrep did not find the fixture text.');
    return 'Searched a local file with the installed native ripgrep';
  }
  throw Error('This catalog entry has no tool check yet.');
}
async function runNativeIndex(p, item, dir, home) {
  await new Promise((resolve, reject) => {
    const child = spawn(executable(p, item), ['reindex', '--no-embed'], { cwd: dir, env: { ...cleanEnv(home), ...item.env }, stdio: 'ignore', windowsHide: true });
    const stop = () => child.kill('SIGKILL'); active.add(stop);
    const timer = setTimeout(stop, 30000);
    child.once('error', () => { clearTimeout(timer); active.delete(stop); reject(Error('Codegraph native engine could not start.')); });
    child.once('close', code => { clearTimeout(timer); active.delete(stop); code === 0 ? resolve() : reject(Error('Codegraph native indexing failed.')); });
  });
}
async function test(request, options = {}) {
  const p = paths(options), item = itemFor(p, request?.id), server = readConfig(p).data.mcp.servers[item.id];
  if (!object(server)) return { ok: false, error: 'Install this server first.' };
  if (busy.has(item.id)) return { ok: false, error: 'An operation for this server is already running.' };
  busy.add(item.id);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ccode-mcp-'));
  const home = path.join(dir, 'home'); fs.mkdirSync(home, { mode: 0o700 });
  let client, transport, timer, timedOut = false;
  const controller = new AbortController(), stop = () => { controller.abort(); void client?.close().catch(() => {}); };
  active.add(stop);
  try {
    fs.writeFileSync(path.join(dir, 'smoke.ts'), 'export function ccodeSmokeAdd(a: number, b: number) { return a + b; }\nconst ccodeSmokeTypeError: number = "wrong";\n');
    fs.writeFileSync(path.join(dir, 'package.json'), '{"name":"ccode-mcp-smoke","version":"1.0.0"}\n');
    fs.writeFileSync(path.join(dir, 'tsconfig.json'), '{"compilerOptions":{"strict":true},"include":["smoke.ts"]}\n');
    if (item.id === 'codegraph') await runNativeIndex(p, item, dir, home);
    const { Client, StdioClientTransport } = await sdk(p);
    client = new Client({ name: 'ccode-mcp-probe', version: '1.0.0' });
    {
      const args = [...(server.args || [])];
      if (args[0] === path.join(p.payload, 'launch.cjs')) args[3] = home;
      transport = new StdioClientTransport({ command: server.command, args, cwd: dir, env: { ...cleanEnv(home), ...server.env }, stderr: 'pipe' });
      transport.stderr?.on('data', () => {});
    }
    const run = async () => {
      await client.connect(transport);
      const tools = [];
      let cursor;
      do { const page = await client.listTools(cursor ? { cursor } : undefined, { timeout: 30000, signal: controller.signal }); tools.push(...page.tools); cursor = page.nextCursor; if (tools.length > 2000) throw Error('Server tool listing exceeded its limit.'); } while (cursor);
      if (!tools.length) throw Error('The server advertised no tools.');
      const message = await probe(client, item, dir, 45000);
      return { ok: true, message, tools: tools.length, probe: item.id, testedAt: Date.now() };
    };
    const result = await Promise.race([run(), new Promise((_, reject) => { timer = setTimeout(() => { timedOut = true; stop(); reject(Error('The MCP operation timed out. Check connectivity and prerequisites.')); }, 100000); })]);
    return result;
  } catch (error) {
    return { ok: false, error: timedOut ? 'The MCP operation timed out. Check connectivity and prerequisites.' : (error.mcpTool ? error.mcpTool + ' failed. ' : '') + 'MCP tools could not be used. Check network access and server prerequisites.' };
  } finally {
    clearTimeout(timer); active.delete(stop);
    await client?.close().catch(() => {}); await transport?.close().catch(() => {});
    fs.rmSync(dir, { recursive: true, force: true }); busy.delete(item.id);
  }
}
function trusted(event) {
  const frame = event.senderFrame;
  if (!frame || frame !== event.sender.mainFrame) return false;
  try {
    const url = new URL(frame.url);
    if (url.protocol !== 'file:') return false;
    // fileURLToPath returns backslashes on Windows and refuses a drive-less file URL there, so
    // the suffix accepts both separators and falls back to the URL path instead of refusing the
    // frame. The URL path is always POSIX, which is why both spellings have to match.
    let path;
    try { path = fileURLToPath(url); } catch { path = url.pathname; }
    return /[\\/]out[\\/]renderer[\\/]index\.html$/.test(path);
  } catch { return false; }
}
function register({ app, ipcMain }) {
  bootstrap();
  for (const [name, operation] of [['list', list], ['install', install]]) ipcMain.handle('ccode-mcp-catalog:' + name, async (event, request) => {
    if (!trusted(event)) throw Error('MCP catalog is only available in the local CCode window.');
    return name === 'list' ? operation() : operation(request);
  });
  app.on('before-quit', () => { for (const stop of active) stop(); });
}
module.exports = { register, bootstrap, list, install, test, paths, definition, trusted,
  DESKTOP_SERVER, DESKTOP_SERVER_LEGACY };
if (require.main === module && process.argv[2] === '--bootstrap') {
  try { bootstrap({ root: process.argv[3], resourcesPath: process.argv[4] }); }
  catch { process.stderr.write('CCode MCP default bootstrap failed. Check the packaged runtime and standalone config.\n'); process.exitCode = 1; }
}
