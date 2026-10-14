'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const runtime = require('../../src/main/mcp-catalog.cjs');
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ccode-mcp-boundary-'));
const resourcesPath = path.join(root, 'resources');
const payload = path.join(resourcesPath, 'mcp');
const catalog = require('./catalog.json');
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
  let saved = JSON.parse(fs.readFileSync(config));
  assert.equal(saved.other, 'keep'); assert.equal(saved.mcp.servers.context7.command, 'user-choice'); assert.equal(saved.mcp.servers.context7.disabled, true);
  assert.equal(saved.mcp.servers.codegraph.command, '/bundled/electron');
  delete saved.mcp.servers.websearch; fs.writeFileSync(config, JSON.stringify(saved));
  runtime.bootstrap(options);
  assert.equal(Object.hasOwn(JSON.parse(fs.readFileSync(config)).mcp.servers, 'websearch'), false);
  assert.equal(runtime.list(options).find(entry => entry.id === 'context7').status, 'disabled');
  assert.throws(() => runtime.validate(catalog[0], { command: 'injection' }), /Unknown/);
  const n8n = catalog.find(entry => entry.id === 'n8n');
  assert.throws(() => runtime.validate(n8n, { url: 'https://secret:password@example.com', apiKey: 'token' }), /embedded credentials/);
  assert.throws(() => runtime.validate(n8n, { url: 'file:///tmp/a', apiKey: 'token' }), /HTTP/);
  const github = catalog.find(entry => entry.id === 'github');
  assert.throws(() => runtime.validate(github, { token: 'x\nHeader: injected' }), /Invalid/);
  assert.equal(runtime.trusted({ sender: { mainFrame: {} }, senderFrame: { url: 'https://evil/out/renderer/index.html' } }), false);
  const frame = { url: 'file:///resources/app.asar/out/renderer/index.html' };
  assert.equal(runtime.trusted({ sender: { mainFrame: frame }, senderFrame: frame }), true);
  const listed = JSON.stringify(runtime.list(options));
  assert.equal(listed.includes('user-choice'), false);
  assert.equal(listed.includes('token'), true); // Field labels, never configured secret values.
  const providerError = runtime.websearchFailure({ structuredContent: { error: 'All web search providers failed: firecrawl: authorization failed (403) SECRET_QUERY; exa: no renderable search content SECRET_KEY; duckduckgo: DNS resolution failed https://secret.example' } });
  assert.equal(providerError.message, 'web_search failed: Firecrawl HTTP 403; Exa returned no search results; DuckDuckGo DNS resolution failed. Keyless provider availability and rate limits vary.');
  assert.equal(providerError.message.includes('SECRET'), false);
} finally { fs.rmSync(root, { recursive: true, force: true }); }
