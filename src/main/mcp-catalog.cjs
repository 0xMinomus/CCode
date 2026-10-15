'use strict';
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const { spawn } = require('node:child_process');
const { pathToFileURL, fileURLToPath } = require('node:url');
const active = new Set(), busy = new Set();
// Computer Use registers itself as `linux-desktop`; the legacy name is only read so an
// install that predates the rename keeps its settings.
const DESKTOP_SERVER = 'linux-desktop', DESKTOP_SERVER_LEGACY = 'fedora-desktop';
function paths(options = {}) {
  const resources = path.resolve(options.resourcesPath || process.resourcesPath || path.join(__dirname, '../../app/resources'));
  const root = path.resolve(options.root || process.env.CCODE_STANDALONE_ROOT || path.join(os.homedir(), '.local/share/ccode'));
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
function projectRoot(resources) {
  for (let dir = path.resolve(resources);; dir = path.dirname(dir)) {
    if (fs.existsSync(path.join(dir, 'project.json'))) return dir;
    if (path.dirname(dir) === dir) return null;
  }
}
// The desktop backend lives beside the application, so its absolute paths depend on where
// the tree sits: a package prefix, a source checkout, or a fresh AppImage mount each run.
function desktopDefinition(resources) {
  if (process.platform !== 'linux') return null;
  const root = projectRoot(resources);
  if (!root) return null;
  const command = path.join(root, 'services/desktop/bin/screen-mcp');
  if (!fs.existsSync(command)) return null;
  return { command, args: [], env: { SCREEN_PYTHON: path.join(root, 'services/desktop/.venv/bin/python'),
    MCP_SCREEN_NO_AUTO_DEPS: '1', MCP_SCREEN_PROFILE: 'ccode-fast', MCP_SCREEN_MAX_EDGE: '1280',
    MCP_SCREEN_MAX_OUTPUT_KB: '250', MCP_SCREEN_ATSPI: '1' } };
}
function applyDesktopDefinition(server, value) {
  server.command = value.command;
  if (!Array.isArray(server.args)) server.args = value.args;
  const env = object(server.env) ? server.env : (server.env = {});
  for (const [name, setting] of Object.entries(value.env)) if (!(name in env)) env[name] = setting;
}
// Seeds the Computer Use server for any layout that ships `services/desktop`. The marker
// keeps a deliberate deletion deleted, while an existing entry is refreshed because an
// AppImage mount point changes between runs.
function seedDesktopServer(resources, snapshot, seeded) {
  if (process.platform !== 'linux') return false;
  const servers = snapshot.data.mcp.servers, value = desktopDefinition(resources);
  const seededBefore = seeded.includes(DESKTOP_SERVER);
  const legacy = servers[DESKTOP_SERVER_LEGACY];
  if (!Object.hasOwn(servers, DESKTOP_SERVER) && object(legacy)) {
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
  for (const item of entries.filter(entry => entry.default)) {
    if (seeded.includes(item.id)) continue;
    if (!fs.existsSync(executable(p, item))) throw Error('Bundled MCP payload is incomplete: ' + item.name);
    if (!Object.hasOwn(snapshot.data.mcp.servers, item.id)) { snapshot.data.mcp.servers[item.id] = definition(p, item); changed = true; }
    seeded.push(item.id);
  }
  if (seedDesktopServer(p.resources, snapshot, seeded)) changed = true;
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
  for (const key of ['PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT']) if (process.env[key]) env[key] = process.env[key];
  return { ...env, HOME: home, XDG_CONFIG_HOME: path.join(home, '.config'), XDG_CACHE_HOME: path.join(home, '.cache'), ELECTRON_RUN_AS_NODE: '1' };
}
function npmInstall(p, item) {
  const dir = runtimePath(p, item), home = path.join(p.state, 'installer-home');
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 }); fs.mkdirSync(home, { recursive: true, mode: 0o700 });
  atomic(path.join(dir, 'package.json'), { name: 'ccode-mcp-' + item.id, version: '1.0.0', private: true, dependencies: { [item.package]: item.version, ...item.dependencies } });
  const npm = path.join(p.payload, 'runtime/node_modules/npm/bin/npm-cli.js');
  return new Promise((resolve, reject) => {
    const child = spawn(p.node, [npm, 'install', '--omit=dev', '--ignore-scripts', '--no-audit', '--no-fund', '--userconfig=' + path.join(home, '.npmrc'), '--cache=' + path.join(p.state, 'npm-cache')], { cwd: dir, env: cleanEnv(home), stdio: 'ignore', detached: process.platform !== 'win32' });
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
    const existing = readConfig(p).data.mcp.servers[item.id];
    const repair = object(existing) && item.package && !fs.existsSync(executable(p, item)) && existing.args?.[0] === path.join(p.payload, 'launch.cjs') && existing.args?.[1] === item.id;
    if (existing && !repair) throw Error('A server with this name already exists. Edit or remove it in the native MCP server list before reinstalling.');
    if (item.package && !item.default) await npmInstall(p, item);
    if (item.package && !fs.existsSync(executable(p, item))) throw Error('The bundled server executable is missing.');
    const snapshot = readConfig(p), servers = snapshot.data.mcp.servers;
    if (repair) {
      if (JSON.stringify(servers[item.id]) !== JSON.stringify(existing)) throw Error('MCP settings changed concurrently. Retry the operation.');
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
    const diagnostics = await call('lsp_diagnostics', { file_path: path.join(dir, 'smoke.ts'), severity_filter: 'all' });
    if (!/2322|not assignable/i.test(textResult(diagnostics))) throw Error('Language server did not report the fixture type error.');
    const found = await call('lsp_document_symbols', { file_path: path.join(dir, 'smoke.ts') });
    if (!textResult(found).includes('ccodeSmokeAdd')) throw Error('Language server did not return the fixture symbol.');
    return 'lsp_document_symbols found the function; lsp_diagnostics reported its known TypeScript type error';
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
    const child = spawn(executable(p, item), ['reindex', '--no-embed'], { cwd: dir, env: { ...cleanEnv(home), ...item.env }, stdio: 'ignore' });
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
  try { const url = new URL(frame.url); return url.protocol === 'file:' && fileURLToPath(url).endsWith('/out/renderer/index.html'); } catch { return false; }
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
