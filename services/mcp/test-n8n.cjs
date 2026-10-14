'use strict';
const assert = require('node:assert/strict');
const { configure } = require('../../src/plugins/n8n/dist/mcp/server.js');
const base = { N8N_API_URL: 'https://n8n.example.test/subpath/', N8N_API_KEY: ' private-key ', CCODE_PLUGIN_DATA: '/tmp/ccode-n8n-test' };
const configured = configure(base);
assert.equal(configured.N8N_API_URL, 'https://n8n.example.test/subpath');
assert.equal(configured.N8N_API_KEY, 'private-key');
assert.equal(configured.N8N_MCP_TELEMETRY_DISABLED, 'true');
assert.equal(configured.HOME, base.CCODE_PLUGIN_DATA);
assert.equal(configure({ ...base, N8N_API_URL: 'http://127.0.0.1:5678' }).N8N_API_URL, 'http://127.0.0.1:5678');
assert.equal(configured.WEBHOOK_SECURITY_MODE, 'strict');
assert.equal(configure({ ...base, N8N_API_URL: 'http://127.0.0.1:5678' }).WEBHOOK_SECURITY_MODE, 'moderate');
for (const url of ['http://remote.example.test', 'https://user:password@n8n.example.test', 'file:///tmp/n8n', 'https://n8n.example.test?key=secret', 'not a URL']) {
  assert.throws(() => configure({ ...base, N8N_API_URL: url }), error => !error.message.includes('private-key') && !error.message.includes('password'));
}
assert.throws(() => configure({ ...base, N8N_API_KEY: '' }), /Set the n8n API key/);
assert.throws(() => configure({ ...base, CCODE_PLUGIN_DATA: '../unsafe' }), /private data directory/);
console.log('n8n launcher: credential, endpoint, telemetry and namespace boundaries passed');
