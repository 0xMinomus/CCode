'use strict';
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const { spawn } = require('node:child_process');
const { pathToFileURL, fileURLToPath } = require('node:url');
const active = new Set(), busy = new Set(), outcomes = new Map();
function paths(options = {}) {
  const resources = path.resolve(options.resourcesPath || process.resourcesPath || path.join(__dirname, '../../app/resources'));
  const root = path.resolve(options.root || process.env.ZCODE_STANDALONE_ROOT || path.join(os.homedir(), '.local/share/ccode'));
  return { resources, root, payload: path.join(resources, 'mcp'), state: path.join(root, 'mcp'), config: path.join(root, 'data/.zcode/cli/config.json'), node: options.node || process.execPath };
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
function definition(p, item, config = {}) {
  if (item.url) return { type: 'http', url: item.url, headers: { Authorization: 'Bearer ' + config.token } };
  const env = { ELECTRON_RUN_AS_NODE: '1', ...item.env };
  if (item.id === 'n8n') Object.assign(env, { N8N_API_URL: config.url, N8N_API_KEY: config.apiKey });
  return { command: p.node, args: [path.join(p.payload, 'launch.cjs'), item.id, runtimePath(p, item), path.join(p.state, 'home', item.id), ...(item.id === 'obsidian' ? [config.vaultPath] : [])], env };
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
  if (changed) commit(p, snapshot);
  atomic(marker, { seeded });
  return { ok: true };
}
function validate(item, value) {
  if (!object(value)) throw Error('MCP configuration must be an object.');
  const keys = item.configFields.map(field => field.key);
  if (Object.keys(value).some(key => !keys.includes(key))) throw Error('Unknown MCP configuration field.');
  const result = {};
  for (const field of item.configFields) {
    const raw = value[field.key];
    if (raw !== undefined && (typeof raw !== 'string' || raw.length > 8192 || /[\0\r\n]/.test(raw))) throw Error('Invalid ' + field.label + '.');
    const text = raw?.trim() || '';
    if (field.required && !text) throw Error(field.label + ' is required.');
    result[field.key] = text;
  }
  if (item.id === 'n8n') {
    let url; try { url = new URL(result.url); } catch { throw Error('Enter a valid n8n base URL.'); }
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw Error('Use an HTTP(S) n8n URL without embedded credentials.');
    result.url = url.href.replace(/\/$/, '');
  }
  if (item.id === 'obsidian' && (!path.isAbsolute(result.vaultPath) || !fs.statSync(result.vaultPath, { throwIfNoEntry: false })?.isDirectory())) throw Error('Select an existing absolute vault folder.');
  return result;
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
    const outcome = outcomes.get(item.id);
    return { id: item.id, name: item.name, description: item.description, default: item.default, installed, configRequired: item.configFields.some(field => field.required), configFields: item.configFields, status: busy.has(item.id) ? 'installing' : !installed ? 'not-installed' : servers[item.id]?.disabled || servers[item.id]?.enabled === false ? 'disabled' : outcome?.ok ? 'usable' : outcome ? 'failed' : 'not-tested', error: outcome?.error || (!present && configured ? 'Installed package is missing. Install again.' : null) };
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
    const config = validate(item, request.config || {});
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
      servers[item.id] = definition(p, item, config);
      commit(p, snapshot);
    }
    outcomes.delete(item.id);
    return { ok: true };
  } catch (error) { return { ok: false, error: error.code ? 'MCP configuration could not be saved. Check file permissions and retry.' : error.message }; }
  finally { busy.delete(item.id); }
}
async function sdk(p) {
  const base = path.join(p.payload, 'runtime/node_modules/@modelcontextprotocol/sdk/dist/esm/client');
  const [{ Client }, { StdioClientTransport }, { StreamableHTTPClientTransport }] = await Promise.all(['index.js', 'stdio.js', 'streamableHttp.js'].map(file => import(pathToFileURL(path.join(base, file)).href)));
  return { Client, StdioClientTransport, StreamableHTTPClientTransport };
}
function textResult(result) { return (result.content || []).filter(part => part.type === 'text').map(part => part.text).join('\n'); }
const SAFE_PROBE_FAILURE = Symbol('safe-probe-failure');
function websearchFailure(result) {
  const detail = String(jsonResult(result)?.error || textResult(result));
  const reasons = [];
  const status = /firecrawl:[^;]*\b(401|403|429|5\d\d)\b/i.exec(detail)?.[1];
  if (status) reasons.push('Firecrawl HTTP ' + status);
  if (/exa:[^;]*no renderable|exa:[^;]*no.*results/i.test(detail)) reasons.push('Exa returned no search results');
  if (/duckduckgo:[^;]*DNS resolution failed/i.test(detail)) reasons.push('DuckDuckGo DNS resolution failed');
  const message = 'web_search failed: ' + (reasons.join('; ') || 'the public search providers returned no usable results') + '. Keyless provider availability and rate limits vary.';
  return Object.assign(Error(message), { [SAFE_PROBE_FAILURE]: true });
}
function jsonResult(result) {
  if (object(result.structuredContent)) return result.structuredContent;
  try { return JSON.parse(textResult(result)); } catch { return null; }
}
function checkResult(result, tool) {
  const text = textResult(result);
  const data = jsonResult(result);
  if (result.isError || data?.error || data?.success === false || /^\s*(Error:|Failed|Unauthorized|Authentication failed)/i.test(text)) {
    if (tool === 'web_search') throw websearchFailure(result);
    throw Error('The server returned a tool error. Check its credentials, connectivity and prerequisites.');
  }
  if (!text.trim() && !result.structuredContent) throw Error('The server returned no tool output.');
  return text;
}
async function probe(client, item, dir, timeout) {
  const call = async (name, args) => {
    try {
      const result = await client.callTool({ name, arguments: args }, undefined, { timeout });
      checkResult(result, name);
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
  if (item.id === 'websearch') {
    const found = await call('web_search', { query: 'Model Context Protocol official documentation', limit: 2 });
    if (!(found.structuredContent?.response?.sources?.length) && !/https?:\/\//.test(textResult(found))) throw websearchFailure(found);
    const fetched = await call('fetch_url', { url: 'https://modelcontextprotocol.io/introduction', max_length: 2000 });
    if (!/context|protocol/i.test(textResult(fetched))) throw Error('URL fetching returned no documentation.');
    return 'Searched public providers and fetched MCP documentation';
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
  if (item.id === 'github') {
    const found = await call('get_me', {});
    if (!/login|username/i.test(textResult(found))) throw Error('GitHub did not return an authenticated account.');
    return 'GitHub authenticated get_me succeeded';
  }
  if (item.id === 'n8n') {
    const health = await call('n8n_health_check', {});
    const status = jsonResult(health);
    if (status?.success !== true || !['ok', 'healthy'].includes(status.data?.status || status.status)) throw Error('n8n instance health check did not succeed.');
    const workflows = jsonResult(await call('n8n_list_workflows', { limit: 1 }));
    if (workflows?.success !== true || !Array.isArray(workflows.data?.workflows)) throw Error('n8n workflow listing did not return a successful API response.');
    return 'Reached the configured n8n instance and listed workflows';
  }
  const found = await call('list_directory', { path: '/' });
  if (!textResult(found).includes('ccode-smoke')) throw Error('Obsidian did not list the temporary vault note.');
  const note = await call('read_note', { path: 'ccode-smoke.md' });
  if (!textResult(note).includes('CCode MCP smoke')) throw Error('Obsidian did not read the temporary vault note.');
  return 'Listed and read a note in an isolated temporary vault';
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
    fs.writeFileSync(path.join(dir, 'smoke.ts'), 'export function ccodeSmokeAdd(a: number, b: number) { return a + b; }\nconst ccodeSmokeTypeError: number = \"wrong\";\n');
    fs.writeFileSync(path.join(dir, 'package.json'), '{"name":"ccode-mcp-smoke","version":"1.0.0"}\n');
    fs.writeFileSync(path.join(dir, 'tsconfig.json'), '{"compilerOptions":{"strict":true},"include":["smoke.ts"]}\n');
    fs.writeFileSync(path.join(dir, 'ccode-smoke.md'), '# CCode MCP smoke\n');
    if (item.id === 'codegraph') await runNativeIndex(p, item, dir, home);
    const { Client, StdioClientTransport, StreamableHTTPClientTransport } = await sdk(p);
    client = new Client({ name: 'ccode-mcp-probe', version: '1.0.0' });
    if (server.url) transport = new StreamableHTTPClientTransport(new URL(server.url), { requestInit: { headers: server.headers || {}, signal: controller.signal } });
    else {
      const args = [...(server.args || [])];
      if (args[0] === path.join(p.payload, 'launch.cjs')) {
        args[3] = home;
        if (item.id === 'obsidian') args.splice(4, args.length - 4, dir);
      }
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
    outcomes.set(item.id, result); return result;
  } catch (error) {
    const result = { ok: false, error: timedOut ? 'The MCP operation timed out. Check connectivity and prerequisites.' : error[SAFE_PROBE_FAILURE] ? error.message : (error.mcpTool ? error.mcpTool + ' failed. ' : '') + 'MCP tools could not be used. Check network access, credentials and server prerequisites.' };
    outcomes.set(item.id, result); return result;
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
  for (const [name, operation] of [['list', list], ['install', install], ['test', test]]) ipcMain.handle('zcode-mcp-catalog:' + name, async (event, request) => {
    if (!trusted(event)) throw Error('MCP catalog is only available in the local CCode window.');
    return name === 'list' ? operation() : operation(request);
  });
  app.on('before-quit', () => { for (const stop of active) stop(); });
}
module.exports = { register, bootstrap, list, install, test, paths, validate, definition, trusted, websearchFailure };
if (require.main === module && process.argv[2] === '--bootstrap') {
  try { bootstrap({ root: process.argv[3], resourcesPath: process.argv[4] }); }
  catch { process.stderr.write('CCode MCP default bootstrap failed. Check the packaged runtime and standalone config.\n'); process.exitCode = 1; }
}
